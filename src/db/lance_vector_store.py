"""Lance 向量存储实现 - 基于 LanceDB 的 VectorStore 接口实现"""

import lancedb
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import pyarrow as pa

from .base import VectorStore
from .schema import STEP_EMBEDDING_SCHEMA
from .cache import VectorCache


class LanceVectorStore(VectorStore):
    """基于 LanceDB 的向量存储，支持批量写入缓冲和内存缓存。"""

    def __init__(
        self,
        db_path: Path,
        table_name: str = "chain_embeddings",
        schema: pa.Schema = STEP_EMBEDDING_SCHEMA,
        flush_threshold: int = 100,
        cache_size: int = 10000
    ):
        self.db_path = db_path
        self.table_name = table_name
        self.schema = schema
        self.flush_threshold = flush_threshold

        # 自动检测主键字段名
        field_names = [f.name for f in schema]
        if "chain_id" in field_names:
            self._id_field = "chain_id"
        elif "step_id" in field_names:
            self._id_field = "step_id"
        else:
            self._id_field = field_names[0]

        self.db_path.mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(str(self.db_path.resolve()))
        self.table = self._ensure_table()
        self.cache = VectorCache(max_size=cache_size)
        self._pending_writes: List[Dict[str, Any]] = []
        self._write_count = 0

    def _ensure_table(self):
        """确保表存在，不存在则创建。"""
        try:
            table = self.db.open_table(self.table_name)
            print(f"Opened existing table: {self.table_name}")
            return table
        except Exception:
            table = self.db.create_table(self.table_name, schema=self.schema)
            print(f"Created new table: {self.table_name}")
            return table

    def add_vectors(
        self,
        ids: List[str],
        vectors: np.ndarray,
        metadata: List[Dict[str, Any]]
    ) -> None:
        if not (len(ids) == len(vectors) == len(metadata)):
            raise ValueError(
                f"Length mismatch: ids={len(ids)}, "
                f"vectors={len(vectors)}, metadata={len(metadata)}"
            )

        for id_, vector, meta in zip(ids, vectors, metadata):
            record = {self._id_field: id_, "vector": vector.tolist(), **meta}
            self._pending_writes.append(record)
            self.cache.put(id_, vector, meta)

        self._write_count += len(ids)
        if len(self._pending_writes) >= self.flush_threshold:
            self.flush()

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        filter_expr: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        if self._pending_writes:
            self.flush()

        query = self.table.search(query_vector.tolist()).limit(top_k)
        if filter_expr:
            query = query.where(filter_expr)

        results = query.to_list()
        return [
            {
                "id": r[self._id_field],
                "distance": r.get("_distance", 0.0),
                "metadata": {k: v for k, v in r.items()
                           if k not in (self._id_field, "vector", "_distance")}
            }
            for r in results
        ]

    def get_by_ids(self, ids: List[str]) -> List[Dict[str, Any]]:
        results = []
        for id_ in ids:
            cached = self.cache.get(id_)
            if cached:
                vector, metadata = cached
                results.append({"id": id_, "vector": vector, "metadata": metadata})
            else:
                if self._pending_writes:
                    self.flush()
                try:
                    db_results = self.table.search().where(
                        f"{self._id_field} = '{id_}'"
                    ).limit(1).to_list()
                    if db_results:
                        result = db_results[0]
                        vector = np.array(result["vector"])
                        metadata = {k: v for k, v in result.items()
                                  if k not in (self._id_field, "vector")}
                        self.cache.put(id_, vector, metadata)
                        results.append({"id": id_, "vector": vector, "metadata": metadata})
                    else:
                        results.append(None)
                except Exception as e:
                    print(f"Error getting vector for id {id_}: {e}")
                    results.append(None)
        return results

    def update_metadata(self, id: str, metadata: Dict[str, Any]) -> None:
        if self._pending_writes:
            self.flush()
        self.table.update(where=f"{self._id_field} = '{id}'", values=metadata)
        self.cache.invalidate({id})

    def batch_update_metadata(
        self, updates: List[Tuple[str, Dict[str, Any]]]
    ) -> None:
        if self._pending_writes:
            self.flush()
        for id_, metadata in updates:
            self.table.update(where=f"{self._id_field} = '{id_}'", values=metadata)
        self.cache.invalidate({id_ for id_, _ in updates})

    def delete(self, ids: List[str]) -> None:
        if self._pending_writes:
            self.flush()
        ids_str = "', '".join(ids)
        self.table.delete(f"{self._id_field} IN ('{ids_str}')")
        self.cache.invalidate(set(ids))

    def count(self, filter_expr: Optional[str] = None) -> int:
        if self._pending_writes:
            self.flush()
        try:
            if filter_expr:
                results = self.table.search().where(filter_expr).to_arrow()
            else:
                results = self.table.to_arrow()
            return len(results)
        except Exception as e:
            print(f"Error counting vectors: {e}")
            return 0

    def flush(self) -> None:
        if not self._pending_writes:
            return
        try:
            self.table.add(self._pending_writes)
            print(f"Flushed {len(self._pending_writes)} records to {self.table_name}")
            self._pending_writes.clear()
        except Exception as e:
            print(f"Error flushing data: {e}")
            raise

    def close(self) -> None:
        if self._pending_writes:
            self.flush()
        self.cache.clear()
        print(f"Closed LanceVectorStore: {self.table_name}")
