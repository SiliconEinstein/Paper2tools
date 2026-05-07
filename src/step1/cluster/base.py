"""聚类抽象与结果类型。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np


@dataclass
class ClusterResult:
    n_clusters: int
    labels: np.ndarray
    step_ids: List[str]
    centers: Optional[np.ndarray]
    metrics: Dict[str, float]


class ClusteringAlgorithm(ABC):
    @abstractmethod
    def fit(self, vectors: np.ndarray) -> np.ndarray:
        pass

    @abstractmethod
    def get_cluster_centers(self) -> Optional[np.ndarray]:
        pass

    @property
    @abstractmethod
    def n_clusters(self) -> int:
        pass
