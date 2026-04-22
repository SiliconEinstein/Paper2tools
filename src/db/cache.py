"""
内存缓存层 - 减少数据库 I/O，提升查询性能

## 设计思想

1. **LRU 淘汰策略**: 当缓存满时，淘汰最久未使用的条目
2. **读写穿透**:
   - 读取时先查缓存，未命中再查数据库
   - 写入时同时更新缓存和数据库
3. **失效策略**:
   - 更新/删除操作主动失效缓存
   - 支持批量失效
4. **统计信息**: 记录命中率、缓存大小等指标

## 使用场景

- 高频查询的向量和元数据
- 聚类中心向量（Step1 聚类时频繁访问）
- 工具匹配结果（Step2 重复查询）

## 性能考虑

- 向量占用内存较大，需要控制缓存大小
- 默认缓存 10000 个向量（假设 768 维，约 30MB）
- 可根据实际内存情况调整 max_size
"""

from typing import Dict, Set, Optional, Any, Tuple
import numpy as np
from collections import OrderedDict
import time


class VectorCache:
    """
    向量查询缓存（LRU 策略）

    缓存结构:
    - _id_to_vector: {step_id: np.ndarray}
    - _id_to_metadata: {step_id: dict}
    - _access_order: OrderedDict，记录访问顺序
    """

    def __init__(self, max_size: int = 10000):
        """
        初始化缓存

        Args:
            max_size: 最大缓存条目数
        """
        self._id_to_vector: Dict[str, np.ndarray] = {}
        self._id_to_metadata: Dict[str, Dict[str, Any]] = {}
        self._access_order: OrderedDict[str, float] = OrderedDict()
        self._max_size = max_size

        # 统计信息
        self._hits = 0
        self._misses = 0

    def get(self, id: str) -> Optional[Tuple[np.ndarray, Dict[str, Any]]]:
        """
        从缓存获取向量和元数据

        Args:
            id: 向量 ID

        Returns:
            (vector, metadata) 元组，如果未命中返回 None
        """
        if id in self._id_to_vector:
            # 命中：更新访问时间
            self._access_order.move_to_end(id)
            self._hits += 1
            return self._id_to_vector[id], self._id_to_metadata[id]
        else:
            # 未命中
            self._misses += 1
            return None

    def put(self, id: str, vector: np.ndarray, metadata: Dict[str, Any]) -> None:
        """
        写入缓存

        Args:
            id: 向量 ID
            vector: 向量数组
            metadata: 元数据字典
        """
        # 如果已存在，先删除（会更新访问顺序）
        if id in self._id_to_vector:
            self._access_order.move_to_end(id)
        else:
            # 检查缓存是否已满
            if len(self._id_to_vector) >= self._max_size:
                self._evict_lru()

            # 添加新条目
            self._access_order[id] = time.time()

        # 更新数据
        self._id_to_vector[id] = vector
        self._id_to_metadata[id] = metadata

    def _evict_lru(self) -> None:
        """淘汰最久未使用的条目"""
        if not self._access_order:
            return

        # 获取最旧的 ID
        lru_id, _ = self._access_order.popitem(last=False)

        # 删除对应数据
        del self._id_to_vector[lru_id]
        del self._id_to_metadata[lru_id]

    def invalidate(self, ids: Set[str]) -> None:
        """
        失效指定 ID 的缓存

        Args:
            ids: 要失效的 ID 集合
        """
        for id in ids:
            if id in self._id_to_vector:
                del self._id_to_vector[id]
                del self._id_to_metadata[id]
                del self._access_order[id]

    def clear(self) -> None:
        """清空缓存"""
        self._id_to_vector.clear()
        self._id_to_metadata.clear()
        self._access_order.clear()
        self._hits = 0
        self._misses = 0

    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            统计信息字典，包含:
            - size: 当前缓存条目数
            - max_size: 最大缓存条目数
            - hits: 命中次数
            - misses: 未命中次数
            - hit_rate: 命中率
        """
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0.0

        return {
            "size": len(self._id_to_vector),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
        }

    def __len__(self) -> int:
        """返回当前缓存条目数"""
        return len(self._id_to_vector)


class MetadataCache:
    """
    元数据缓存（简单的字典缓存，无 LRU）

    用于缓存小型元数据（进度追踪、聚类统计等），
    这些数据通常不会太大，可以全部缓存在内存中。
    """

    def __init__(self):
        self._cache: Dict[str, Any] = {}

    def get(self, key: str) -> Optional[Any]:
        """获取元数据"""
        return self._cache.get(key)

    def set(self, key: str, value: Any) -> None:
        """设置元数据"""
        self._cache[key] = value

    def delete(self, keys: Set[str]) -> None:
        """删除指定键"""
        for key in keys:
            self._cache.pop(key, None)

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)
