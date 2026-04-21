"""
数据库模块 - Lance 向量数据库操作的抽象层

## 设计原则

1. **接口与实现分离**: 定义抽象基类，具体实现可替换
2. **Schema 独立定义**: PyArrow schema 单独文件，避免循环依赖
3. **内存缓存层**: 高频查询字段缓存到内存，减少数据库 I/O
4. **TOS 同步机制**: 支持本地 Lance 数据库与 TOS 的增量同步
5. **事务性操作**: 批量写入、flush 控制、异常回滚

## 模块结构

- `base.py`: 抽象基类（VectorStore, MetadataStore）
- `lance_vector_store.py`: Lance 向量存储实现
- `lance_metadata_store.py`: Lance 元数据存储实现
- `schema.py`: PyArrow schema 定义
- `cache.py`: 内存缓存层
- `sync.py`: TOS 同步管理器
- `config.py`: 数据库配置

## 使用示例

```python
from src.db import LanceVectorStore, LanceDBConfig

# 初始化配置
config = LanceDBConfig(
    local_db_dir=Path("data/lance_db"),
    tos_bucket="wenyon-paper",
    tos_prefix="paper_ocr/lance/step1/",
    flush_every=100
)

# 创建向量存储
store = LanceVectorStore(config.local_db_dir, table_name="step_embeddings")

# 添加向量
store.add_vectors(
    ids=["paper1_c1_s1", "paper1_c1_s2"],
    vectors=np.array([[0.1, 0.2, ...], [0.3, 0.4, ...]]),
    metadata=[
        {"paper_id": "paper1", "journal": "Bioinformatics", ...},
        {"paper_id": "paper1", "journal": "Bioinformatics", ...}
    ]
)

# 向量搜索
results = store.search(
    query_vector=np.array([0.15, 0.25, ...]),
    top_k=10,
    filter_expr="journal = 'Bioinformatics'"
)

# 持久化
store.flush()
```
"""

from .base import VectorStore, MetadataStore
from .lance_vector_store import LanceVectorStore
from .lance_metadata_store import LanceMetadataStore
from .config import LanceDBConfig
from .sync import LanceTosSync
from .cache import VectorCache

__all__ = [
    "VectorStore",
    "MetadataStore",
    "LanceVectorStore",
    "LanceMetadataStore",
    "LanceDBConfig",
    "LanceTosSync",
    "VectorCache",
]
