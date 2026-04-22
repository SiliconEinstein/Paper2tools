"""
数据库配置 - Lance 数据库的配置参数

## 配置项说明

### 本地存储
- local_db_dir: 本地数据库目录（Lance 数据库文件存放位置）

### TOS 同步
- tos_bucket: TOS bucket 名称
- tos_prefix: TOS 对象前缀（数据库文件在 TOS 中的路径）
- enable_tos_sync: 是否启用 TOS 同步
- sync_on_close: 关闭数据库时是否自动同步到 TOS

### 性能参数
- flush_every: 每 N 次写入操作后 flush 一次
- cache_size: 内存缓存大小（缓存的向量数量）
- batch_size: 批量写入的批次大小

### 向量参数
- embedding_dim: 向量维度（取决于使用的 embedding 模型）
"""

from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LanceDBConfig:
    """
    Lance 数据库配置

    使用示例:
    ```python
    config = LanceDBConfig(
        local_db_dir=Path("data/lance_db"),
        tos_bucket="wenyon-paper",
        tos_prefix="paper_ocr/lance/step1/"
    )
    ```
    """

    # ========== 本地存储 ==========
    local_db_dir: Path
    """本地数据库目录"""

    # ========== TOS 同步 ==========
    tos_bucket: str = "wenyon-paper"
    """TOS bucket 名称"""

    tos_prefix: str = "paper_ocr/lance/"
    """TOS 对象前缀"""

    enable_tos_sync: bool = True
    """是否启用 TOS 同步"""

    sync_on_close: bool = True
    """关闭数据库时是否自动同步到 TOS"""

    # ========== 性能参数 ==========
    flush_every: int = 100
    """每 N 次写入操作后 flush 一次"""

    cache_size: int = 10000
    """内存缓存大小（缓存的向量数量）"""

    batch_size: int = 1000
    """批量写入的批次大小"""

    # ========== 向量参数 ==========
    embedding_dim: Optional[int] = None
    """向量维度（如果为 None，从第一次写入的向量推断）"""

    # ========== 其他 ==========
    verbose: bool = True
    """是否打印详细日志"""

    def __post_init__(self):
        """初始化后处理：确保路径是 Path 对象"""
        if not isinstance(self.local_db_dir, Path):
            self.local_db_dir = Path(self.local_db_dir)

        # 创建本地目录（如果不存在）
        self.local_db_dir.mkdir(parents=True, exist_ok=True)

    def get_table_path(self, table_name: str) -> Path:
        """
        获取指定表的本地路径

        Args:
            table_name: 表名（如 "step_embeddings"）

        Returns:
            表的本地路径
        """
        return self.local_db_dir / f"{table_name}.lance"

    def get_tos_table_prefix(self, table_name: str) -> str:
        """
        获取指定表在 TOS 中的前缀

        Args:
            table_name: 表名

        Returns:
            TOS 前缀（如 "paper_ocr/lance/step_embeddings.lance/"）
        """
        return f"{self.tos_prefix}{table_name}.lance/"


@dataclass
class VectorStoreConfig:
    """
    向量存储配置（更高层的配置，包含多个表）

    使用示例:
    ```python
    config = VectorStoreConfig(
        db_config=LanceDBConfig(...),
        step_embedding_table="step_embeddings",
        cluster_center_table="cluster_centers"
    )
    ```
    """

    db_config: LanceDBConfig
    """底层数据库配置"""

    # ========== 表名配置 ==========
    step_embedding_table: str = "step_embeddings"
    """推理步骤 embedding 表名"""

    cluster_center_table: str = "cluster_centers"
    """聚类中心表名"""

    progress_tracker_table: str = "progress_tracker"
    """进度追踪表名"""

    tool_match_table: str = "tool_matches"
    """工具匹配结果表名"""
