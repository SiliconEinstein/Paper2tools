"""
RAPIDS cuML GPU 聚类（可选）。请通过 ``clustering.create_clustering_algorithm(device=...)`` 选择。
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from .base import ClusteringAlgorithm


def is_cuml_kmeans_available() -> bool:
    """当前环境是否可加载 cuML 的 MiniBatchKMeans（通常需 NVIDIA GPU + CUDA）。"""
    try:
        from cuml.cluster import MiniBatchKMeans  # noqa: F401

        return True
    except Exception:
        return False


def is_cuml_hdbscan_available() -> bool:
    """当前环境是否可加载 cuML 的 GPU HDBSCAN。"""
    try:
        from cuml.cluster.hdbscan import HDBSCAN  # noqa: F401

        return True
    except Exception:
        return False


def _as_numpy(x: Any) -> np.ndarray:
    """cuML/cuPy 输出 → host numpy。"""
    if x is None:
        raise ValueError("unexpected None from cuML")
    if isinstance(x, np.ndarray):
        return np.asarray(x)
    if hasattr(x, "get"):
        return np.asarray(x.get())
    return np.asarray(x)


class CumlMiniBatchKMeansClustering(ClusteringAlgorithm):
    """与 KMeansClustering 接口一致，底层为 cuML MiniBatchKMeans（GPU）。"""

    def __init__(
        self,
        n_clusters: int,
        random_seed: int = 42,
        batch_size: int = 10000,
        max_iter: int = 300,
    ):
        from cuml.cluster import MiniBatchKMeans as CuMiniBatchKMeans

        self._n_clusters = int(n_clusters)
        self.model = CuMiniBatchKMeans(
            n_clusters=self._n_clusters,
            batch_size=int(batch_size),
            max_iter=int(max_iter),
            random_state=random_seed,
        )

    def fit(self, vectors: np.ndarray) -> np.ndarray:
        x = np.ascontiguousarray(np.asarray(vectors, dtype=np.float32))
        labels = self.model.fit_predict(x)
        return _as_numpy(labels).astype(np.int32, copy=False)

    def get_cluster_centers(self) -> Optional[np.ndarray]:
        centers = self.model.cluster_centers_
        if centers is None:
            return None
        return _as_numpy(centers).astype(np.float32, copy=False)

    @property
    def n_clusters(self) -> int:
        return self._n_clusters


class CumlHDBSCANClustering(ClusteringAlgorithm):
    """cuML GPU HDBSCAN；cuML 仅支持 ``metric='euclidean'``。

    若配置 ``metric='cosine'``，则在 GPU 上对行向量做 L2 归一化后再聚类（常见近似）；
    **质心在原始未归一化向量上按簇求均值**，以便与 Lance 中存储的向量及选样距离一致。
    """

    def __init__(
        self,
        min_cluster_size: int = 10,
        min_samples: Optional[int] = None,
        metric: str = "euclidean",
        cluster_selection_epsilon: float = 0.0,
        cluster_selection_method: str = "eom",
        build_algo: str = "nn_descent",
    ):
        from cuml.cluster.hdbscan import HDBSCAN as CuHDBSCAN

        self._metric = (metric or "euclidean").lower().strip()
        self._l2_normalize = self._metric in ("cosine", "angular")
        self._X_orig: Optional[np.ndarray] = None
        ms = int(min_samples) if min_samples is not None else None
        self.model = CuHDBSCAN(
            min_cluster_size=int(min_cluster_size),
            min_samples=ms,
            cluster_selection_epsilon=float(cluster_selection_epsilon),
            cluster_selection_method=str(cluster_selection_method),
            metric="euclidean",
            build_algo=str(build_algo),
        )
        self._n_clusters = 0

    def fit(self, vectors: np.ndarray) -> np.ndarray:
        from sklearn.preprocessing import normalize

        x_orig = np.ascontiguousarray(np.asarray(vectors, dtype=np.float32))
        self._X_orig = x_orig
        x = x_orig
        if self._l2_normalize:
            x = normalize(x_orig, norm="l2", axis=1, copy=True).astype(np.float32)
        labels = self.model.fit_predict(x)
        lab = _as_numpy(labels).astype(np.int64, copy=False).ravel()
        self._fit_labels = lab
        uniq = np.unique(lab)
        noise = uniq.size > 0 and np.min(uniq) == -1
        self._n_clusters = int(uniq.size - (1 if noise else 0))
        return lab.astype(np.int32, copy=False)

    def get_cluster_centers(self) -> Optional[np.ndarray]:
        if self._X_orig is None or not hasattr(self, "_fit_labels"):
            return None
        labels_arr = self._fit_labels
        unique_labels = sorted(set(labels_arr.tolist()) - {-1})
        if not unique_labels:
            return None
        xo = self._X_orig
        centers = []
        for lab in unique_labels:
            mask = labels_arr == lab
            centers.append(xo[mask].mean(axis=0))
        return np.asarray(centers, dtype=np.float32)

    @property
    def n_clusters(self) -> int:
        return self._n_clusters
