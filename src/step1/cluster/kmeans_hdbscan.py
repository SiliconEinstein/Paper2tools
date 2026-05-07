"""KMeans / HDBSCAN 实现。"""

from typing import Optional

import numpy as np
import hdbscan
from sklearn.cluster import KMeans, MiniBatchKMeans

from .base import ClusteringAlgorithm


class KMeansClustering(ClusteringAlgorithm):
    def __init__(self, n_clusters: int, random_seed: int = 42, mini_batch: bool = True, batch_size: int = 10000):
        if mini_batch:
            self.model = MiniBatchKMeans(
                n_clusters=n_clusters, random_state=random_seed,
                batch_size=batch_size, n_init=3, max_iter=300
            )
        else:
            self.model = KMeans(n_clusters=n_clusters, random_state=random_seed, n_init=3)
        self._n_clusters = n_clusters

    def fit(self, vectors: np.ndarray) -> np.ndarray:
        return self.model.fit_predict(vectors)

    def get_cluster_centers(self) -> np.ndarray:
        return self.model.cluster_centers_

    @property
    def n_clusters(self) -> int:
        return self._n_clusters


class HDBSCANClustering(ClusteringAlgorithm):
    def __init__(
        self,
        min_cluster_size: int = 10,
        min_samples: int = 5,
        metric: str = 'euclidean',
        cluster_selection_epsilon: float = 0.0,
        cluster_selection_method: str = 'eom'
    ):
        """
        HDBSCAN 聚类算法

        Args:
            min_cluster_size: 最小簇大小（簇至少包含多少样本）
            min_samples: 最小样本数（邻域内至少多少样本才是核心点）
            metric: 距离度量 ('euclidean', 'cosine', 'manhattan' 等)
            cluster_selection_epsilon: 簇选择阈值（小于此值的簇会被合并，0.0表示不强制合并）
            cluster_selection_method: 簇选择方法 ('eom' 或 'leaf')
        """
        self._requested_metric = metric
        # CPU hdbscan BallTree 不支持 cosine；改用 L2 归一化 + euclidean（等价）
        actual_metric = 'euclidean' if metric == 'cosine' else metric
        self.model = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=min_samples,
            metric=actual_metric,
            cluster_selection_epsilon=cluster_selection_epsilon,
            cluster_selection_method=cluster_selection_method
        )
        self._n_clusters = 0

    def fit(self, vectors: np.ndarray) -> np.ndarray:
        if self._requested_metric == 'cosine':
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            vectors = vectors / norms
        labels = self.model.fit_predict(vectors)
        self._n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        return labels

    def get_cluster_centers(self) -> Optional[np.ndarray]:
        if not hasattr(self.model, 'labels_'):
            return None
        labels = self.model.labels_
        unique_labels = sorted(set(labels) - {-1})
        if not unique_labels:
            return None
        centers = []
        for label in unique_labels:
            mask = labels == label
            centers.append(self.model._raw_data[mask].mean(axis=0))
        return np.array(centers)

    @property
    def n_clusters(self) -> int:
        return self._n_clusters
