"""Lance 向量存储实现 - 基于 LanceDB 的 VectorStore 接口实现"""

import lancedb
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Iterator
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
        flush_threshold: int = 1000,
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
        elif "workflow_id" in field_names:
            self._id_field = "workflow_id"
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

    @property
    def id_field(self) -> str:
        """主键列名（如 ``chain_id``）。"""
        return self._id_field

    def iter_embedding_pages(self, page_size: int = 32768) -> Iterator[pa.Table]:
        """
        顺序分页遍历整张表，每次只含 ``{id_field, vector}`` 列。

        用于簇选择等「一次顺序读 + 内存过滤」场景，避免对每个簇单独 ``WHERE IN``。
        """
        if self._pending_writes:
            self.flush()
        offset = 0
        cols = [self._id_field, "vector"]
        while True:
            ar = (
                self.table.search()
                .select(cols)
                .limit(page_size)
                .offset(offset)
                .to_arrow()
            )
            n = len(ar)
            if n == 0:
                break
            yield ar
            offset += n
            if n < page_size:
                break

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

        # 批量 tolist() 避免逐条序列化开销
        vectors_list = vectors.tolist()
        for id_, vector_list, vector_np, meta in zip(ids, vectors_list, vectors, metadata):
            record = {self._id_field: id_, "vector": vector_list, **meta}
            self._pending_writes.append(record)
            self.cache.put(id_, vector_np, meta)

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

        query = self.table.search(query_vector.tolist(), vector_column_name="vector").limit(top_k)
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
        """批量获取向量，优先从缓存，缺失的批量从 DB 查询"""
        results = []
        missing_ids = []
        id_to_idx = {}

        # 先从缓存取
        for idx, id_ in enumerate(ids):
            cached = self.cache.get(id_)
            if cached:
                vector, metadata = cached
                results.append({"id": id_, "vector": vector, "metadata": metadata})
            else:
                results.append(None)
                missing_ids.append(id_)
                id_to_idx[id_] = idx

        # 批量查询缺失的
        if missing_ids:
            if self._pending_writes:
                self.flush()

            batch_size = 5000
            for batch_start in range(0, len(missing_ids), batch_size):
                batch_ids = missing_ids[batch_start:batch_start + batch_size]
                ids_str = "', '".join(batch_ids)
                filter_expr = f"{self._id_field} IN ('{ids_str}')"
                try:
                    db_results = self.table.search().where(filter_expr).limit(len(batch_ids)).to_list()
                    for result in db_results:
                        id_ = result[self._id_field]
                        vector = np.array(result["vector"], dtype=np.float32)
                        metadata = {k: v for k, v in result.items()
                                  if k not in (self._id_field, "vector")}
                        self.cache.put(id_, vector, metadata)
                        idx = id_to_idx[id_]
                        results[idx] = {"id": id_, "vector": vector, "metadata": metadata}
                except Exception as e:
                    print(f"Error getting batch of vectors: {e}")

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
        """行数统计；无 filter 时用 ``count_rows()``，避免 ``to_arrow()`` 全表加载。"""
        if self._pending_writes:
            self.flush()
        try:
            if filter_expr:
                return len(
                    self.table.search().where(filter_expr).limit(999_999_999).to_arrow()
                )
            return int(self.table.count_rows())
        except Exception as e:
            print(f"Error counting vectors: {e}")
            return 0

    def _fetch_by_ids_table_scan(
        self,
        id_set: set,
        select_cols: List[str],
        columns: List[str],
        page_size: int,
        verbose: bool,
    ) -> Dict[str, Dict[str, Any]]:
        """
        顺序分页扫描全表，只保留 id_set 中的行。适合「待取 ID 很多、接近全表」的场景，
        避免数百次 ``IN (...)`` 各自触发表扫描。
        """
        out: Dict[str, Dict[str, Any]] = {}
        offset = 0
        target_n = len(id_set)
        pages = 0
        while len(out) < target_n:
            try:
                ar = (
                    self.table.search()
                    .select(select_cols)
                    .limit(page_size)
                    .offset(offset)
                    .to_arrow()
                )
            except Exception as e:
                print(f"_fetch_by_ids_table_scan error at offset={offset}: {e}")
                break
            n = len(ar)
            if n == 0:
                break
            id_col = ar.column(self._id_field)
            col_arrays = {c: ar.column(c) for c in select_cols}
            for row_idx in range(n):
                rid = id_col[row_idx].as_py()
                sr = str(rid)
                if sr not in id_set or sr in out:
                    continue
                rec: Dict[str, Any] = {}
                for c in columns:
                    v = col_arrays[c][row_idx].as_py()
                    if c == "vector" and v is not None:
                        v = np.asarray(v, dtype=np.float32)
                    rec[c] = v
                out[sr] = rec
            offset += n
            pages += 1
            if verbose and pages % 2 == 0:
                print(
                    f"  ... table scan: matched {len(out)}/{target_n} ids, "
                    f"rows_scanned≈{offset}",
                    flush=True,
                )
            if n < page_size:
                break
        return out

    def fetch_by_ids_batched(
        self,
        ids: List[str],
        columns: Optional[List[str]] = None,
        batch_size: int = 2500,
        *,
        scan_if_id_count_ge: int = 80000,
        scan_page_size: int = 32768,
        verbose: bool = False,
    ) -> Dict[str, Dict[str, Any]]:
        """
        按 ID 拉取列。

        - ID 数量 **小于** ``scan_if_id_count_ge``：用 ``WHERE IN`` 分批查询。
        - ID 数量 **较大**（例如簇选择要拉二十万+向量）：改为 **顺序全表分页扫描**，
          通常比数百次 ``IN`` 更快。

        注意：不能用 ``pyarrow.dataset.dataset(table.to_lance())``，PyArrow 不接受
        ``LanceDataset``。
        """
        if not ids:
            return {}
        if self._pending_writes:
            self.flush()

        if columns is None:
            columns = ["paper_id", "chain_text"]

        select_cols: List[str] = []
        seen = set()
        for c in [self._id_field] + list(columns):
            if c not in seen:
                seen.add(c)
                select_cols.append(c)

        id_set = {str(x) for x in ids}
        if len(id_set) >= scan_if_id_count_ge:
            if verbose:
                print(
                    f"  (large id set: {len(id_set)} → table scan, page={scan_page_size})",
                    flush=True,
                )
            return self._fetch_by_ids_table_scan(
                id_set, select_cols, columns, scan_page_size, verbose
            )

        out: Dict[str, Dict[str, Any]] = {}
        id_list = list(ids)
        for i in range(0, len(id_list), batch_size):
            chunk = id_list[i : i + batch_size]
            esc = "', '".join(str(x).replace("'", "''") for x in chunk)
            where = f"{self._id_field} IN ('{esc}')"
            try:
                ar = (
                    self.table.search()
                    .select(select_cols)
                    .where(where)
                    .limit(len(chunk))
                    .to_arrow()
                )
            except Exception as e:
                print(f"fetch_by_ids_batched error batch {i}: {e}")
                continue

            id_col = ar.column(self._id_field).to_pylist()
            col_arrays = {c: ar.column(c).to_pylist() for c in select_cols}
            for row_idx, rid in enumerate(id_col):
                rec: Dict[str, Dict[str, Any]] = {}
                for c in columns:
                    v = col_arrays[c][row_idx]
                    if c == "vector" and v is not None:
                        v = np.asarray(v, dtype=np.float32)
                    rec[c] = v
                out[str(rid)] = rec

        return out

    def all_id_values_pylist(self) -> List[str]:
        """仅扫描主键列（用于增量向量化判断已存在 id）。"""
        if self._pending_writes:
            self.flush()
        col = self._id_field
        arrow = self.table.search().select([col]).to_arrow()
        return arrow.column(col).to_pylist()

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
