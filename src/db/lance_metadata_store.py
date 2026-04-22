"""Lance 元数据存储实现 - 用于进度追踪、统计信息等非向量数据"""

import lancedb
from pathlib import Path
from typing import List, Dict, Any, Optional
import pyarrow as pa

from .base import MetadataStore
from .schema import PROGRESS_TRACKER_SCHEMA
from .cache import MetadataCache


class LanceMetadataStore(MetadataStore):
    """基于 LanceDB 普通表的元数据存储（无向量字段）。"""

    def __init__(
        self,
        db_path: Path,
        table_name: str = "progress_tracker",
        schema: pa.Schema = PROGRESS_TRACKER_SCHEMA
    ):
        self.db_path = db_path
        self.table_name = table_name
        self.schema = schema

        self.db_path.mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(str(self.db_path.resolve()))
        self.table = self._ensure_table()
        self.cache = MetadataCache()

    def _ensure_table(self):
        try:
            table = self.db.open_table(self.table_name)
            print(f"Opened existing metadata table: {self.table_name}")
            return table
        except Exception:
            table = self.db.create_table(self.table_name, schema=self.schema)
            print(f"Created new metadata table: {self.table_name}")
            return table

    @property
    def _pk_field(self) -> str:
        """主键字段名（schema 的第一个字段）。"""
        return self.schema.names[0]

    def get(self, key: str) -> Optional[Any]:
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        try:
            results = self.table.search().where(
                f"{self._pk_field} = '{key}'"
            ).limit(1).to_list()
            if results:
                self.cache.set(key, results[0])
                return results[0]
            return None
        except Exception as e:
            print(f"Error getting metadata for key {key}: {e}")
            return None

    def set(self, key: str, value: Any) -> None:
        existing = self.get(key)
        if existing:
            self.table.update(
                where=f"{self._pk_field} = '{key}'",
                values=value
            )
        else:
            record = {self._pk_field: key, **value}
            self.table.add([record])
        self.cache.set(key, value)

    def batch_update(self, updates: Dict[str, Any]) -> None:
        for key, value in updates.items():
            self.set(key, value)

    def query(
        self,
        filter_expr: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        query = self.table.search().where(filter_expr)
        if limit:
            query = query.limit(limit)
        return query.to_list()

    def delete(self, keys: List[str]) -> None:
        keys_str = "', '".join(keys)
        self.table.delete(f"{self._pk_field} IN ('{keys_str}')")
        self.cache.delete(set(keys))

    def flush(self) -> None:
        pass  # LanceDB 自动持久化

    def close(self) -> None:
        self.cache.clear()
        print(f"Closed LanceMetadataStore: {self.table_name}")
