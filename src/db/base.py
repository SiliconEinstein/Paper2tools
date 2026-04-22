"""
抽象基类 - 定义向量存储和元数据存储的统一接口

## 设计思想

遵循依赖倒置原则（Dependency Inversion Principle）：
- 高层模块（Step1/Step2/Step3）依赖抽象接口，不依赖具体实现
- 具体实现（LanceVectorStore）依赖抽象接口
- 可以轻松替换底层存储引擎（Lance → Chroma → Milvus）

## 接口职责

### VectorStore
负责向量的存储、检索、更新、删除操作。
核心场景：
- Step1: 存储推理步骤的 embedding 向量
- Step1: 基于向量相似度进行聚类
- Step2/Step3: 根据向量检索相似步骤

### MetadataStore
负责元数据的存储和查询（进度追踪、统计信息等）。
核心场景：
- 记录每篇论文的处理进度（step1/step2/step3 完成状态）
- 存储聚类中心、聚类统计信息
- 记录工具匹配结果的元数据
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
import numpy as np


class VectorStore(ABC):
    """
    向量存储抽象接口

    所有向量存储实现必须继承此类并实现所有抽象方法。
    """

    @abstractmethod
    def add_vectors(
        self,
        ids: List[str],
        vectors: np.ndarray,
        metadata: List[Dict[str, Any]]
    ) -> None:
        """
        批量添加向量

        Args:
            ids: 向量 ID 列表（唯一标识符）
            vectors: 向量矩阵，shape = (len(ids), embedding_dim)
            metadata: 每个向量的元数据字典列表

        Raises:
            ValueError: 如果 ids、vectors、metadata 长度不一致
            DuplicateKeyError: 如果 ID 已存在（取决于实现策略）
        """
        pass

    @abstractmethod
    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        filter_expr: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        向量相似度搜索（ANN - Approximate Nearest Neighbor）

        Args:
            query_vector: 查询向量，shape = (embedding_dim,)
            top_k: 返回最相似的 top_k 个结果
            filter_expr: 过滤表达式（SQL-like 语法，如 "journal = 'Bioinformatics'"）

        Returns:
            结果列表，每个元素包含：
            - id: 向量 ID
            - distance: 距离（越小越相似）
            - metadata: 元数据字典
        """
        pass

    @abstractmethod
    def get_by_ids(self, ids: List[str]) -> List[Dict[str, Any]]:
        """
        根据 ID 批量获取向量和元数据

        Args:
            ids: 向量 ID 列表

        Returns:
            结果列表，每个元素包含：
            - id: 向量 ID
            - vector: 向量（np.ndarray）
            - metadata: 元数据字典

            如果某个 ID 不存在，对应位置返回 None
        """
        pass

    @abstractmethod
    def update_metadata(
        self,
        id: str,
        metadata: Dict[str, Any]
    ) -> None:
        """
        更新指定 ID 的元数据（不更新向量本身）

        Args:
            id: 向量 ID
            metadata: 新的元数据字典（会与现有元数据合并）

        Raises:
            KeyError: 如果 ID 不存在
        """
        pass

    @abstractmethod
    def batch_update_metadata(
        self,
        updates: List[Tuple[str, Dict[str, Any]]]
    ) -> None:
        """
        批量更新元数据

        Args:
            updates: [(id, metadata), ...] 列表
        """
        pass

    @abstractmethod
    def delete(self, ids: List[str]) -> None:
        """
        删除指定 ID 的向量

        Args:
            ids: 要删除的向量 ID 列表
        """
        pass

    @abstractmethod
    def count(self, filter_expr: Optional[str] = None) -> int:
        """
        统计向量数量

        Args:
            filter_expr: 过滤表达式（可选）

        Returns:
            向量数量
        """
        pass

    @abstractmethod
    def flush(self) -> None:
        """
        将缓冲区的数据持久化到磁盘

        某些实现（如 Lance）支持批量写入缓冲，
        调用此方法强制刷新到磁盘。
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """
        关闭数据库连接，释放资源
        """
        pass


class MetadataStore(ABC):
    """
    元数据存储抽象接口

    用于存储非向量数据，如进度追踪、统计信息、聚类中心等。
    """

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """
        获取单个元数据

        Args:
            key: 元数据键

        Returns:
            元数据值，如果不存在返回 None
        """
        pass

    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """
        设置单个元数据

        Args:
            key: 元数据键
            value: 元数据值
        """
        pass

    @abstractmethod
    def batch_update(self, updates: Dict[str, Any]) -> None:
        """
        批量更新元数据

        Args:
            updates: {key: value, ...} 字典
        """
        pass

    @abstractmethod
    def query(
        self,
        filter_expr: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        条件查询元数据

        Args:
            filter_expr: 过滤表达式（SQL-like 语法）
            limit: 返回结果数量限制

        Returns:
            符合条件的元数据列表
        """
        pass

    @abstractmethod
    def delete(self, keys: List[str]) -> None:
        """
        删除指定键的元数据

        Args:
            keys: 要删除的键列表
        """
        pass

    @abstractmethod
    def flush(self) -> None:
        """持久化到磁盘"""
        pass

    @abstractmethod
    def close(self) -> None:
        """关闭连接"""
        pass
