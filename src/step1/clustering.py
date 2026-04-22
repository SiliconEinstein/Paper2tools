"""
聚类算法模块 - 对向量化后的推理步骤进行语义聚类
"""

import json
import numpy as np
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Optional

from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score, calinski_harabasz_score, davies_bouldin_score
import hdbscan
import umap

from ..db import LanceVectorStore


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


class KMeansClustering(ClusteringAlgorithm):
    def __init__(self, n_clusters: int, random_seed: int = 42):
        self.model = KMeans(n_clusters=n_clusters, random_state=random_seed, n_init=10)
        self._n_clusters = n_clusters

    def fit(self, vectors: np.ndarray) -> np.ndarray:
        return self.model.fit_predict(vectors)

    def get_cluster_centers(self) -> np.ndarray:
        return self.model.cluster_centers_

    @property
    def n_clusters(self) -> int:
        return self._n_clusters


class HDBSCANClustering(ClusteringAlgorithm):
    def __init__(self, min_cluster_size: int = 10, min_samples: int = 5):
        self.model = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=min_samples
        )
        self._n_clusters = 0

    def fit(self, vectors: np.ndarray) -> np.ndarray:
        labels = self.model.fit_predict(vectors)
        self._n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        return labels

    def get_cluster_centers(self) -> Optional[np.ndarray]:
        # 计算各簇质心
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


def create_clustering_algorithm(config: Dict) -> ClusteringAlgorithm:
    """工厂函数，根据配置创建聚类器"""
    algo = config["algorithm"]
    if algo == "kmeans":
        k = config.get("n_clusters")
        if k is None:
            raise ValueError("n_clusters required for kmeans")
        return KMeansClustering(
            n_clusters=k,
            random_seed=config.get("random_seed", 42)
        )
    elif algo == "hdbscan":
        return HDBSCANClustering(
            min_cluster_size=config["hdbscan"]["min_cluster_size"],
            min_samples=config["hdbscan"]["min_samples"]
        )
    else:
        raise ValueError(f"Unknown clustering algorithm: {algo}")


def evaluate_clustering(vectors: np.ndarray, labels: np.ndarray, sample_size: int = 10000) -> Dict[str, float]:
    """计算聚类质量指标（大规模数据用采样 silhouette）"""
    valid_mask = labels >= 0
    valid_vectors = vectors[valid_mask]
    valid_labels = labels[valid_mask]
    n_valid_clusters = len(set(valid_labels))

    metrics = {
        "n_clusters": n_valid_clusters,
        "n_noise": int((labels == -1).sum()),
        "n_total": len(labels),
        "noise_ratio": float((labels == -1).sum()) / len(labels) if len(labels) > 0 else 0.0,
    }

    # 簇大小分布统计
    cluster_sizes = Counter(int(l) for l in valid_labels)
    sizes = sorted(cluster_sizes.values())
    if sizes:
        metrics["cluster_size_min"] = sizes[0]
        metrics["cluster_size_max"] = sizes[-1]
        metrics["cluster_size_median"] = float(np.median(sizes))
        metrics["cluster_size_mean"] = float(np.mean(sizes))

    if n_valid_clusters >= 2:
        # 采样 silhouette（避免 O(n²) OOM）
        n = len(valid_vectors)
        if n > sample_size:
            idx = np.random.RandomState(42).choice(n, sample_size, replace=False)
            metrics["silhouette"] = float(silhouette_score(valid_vectors[idx], valid_labels[idx]))
            metrics["silhouette_sample_size"] = sample_size
        else:
            metrics["silhouette"] = float(silhouette_score(valid_vectors, valid_labels))
            metrics["silhouette_sample_size"] = n

        metrics["calinski_harabasz"] = float(calinski_harabasz_score(valid_vectors, valid_labels))
        metrics["davies_bouldin"] = float(davies_bouldin_score(valid_vectors, valid_labels))

    return metrics


def find_optimal_k(
    vectors: np.ndarray,
    min_k: int = 5,
    max_k: int = 50,
    method: str = "silhouette"
) -> int:
    """自动搜索最优聚类数"""
    best_k, best_score = min_k, -1.0

    for k in range(min_k, max_k + 1):
        model = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = model.fit_predict(vectors)
        score = silhouette_score(vectors, labels)
        print(f"  k={k}: silhouette={score:.4f}")
        if score > best_score:
            best_score, best_k = score, k

    print(f"Optimal k={best_k} (silhouette={best_score:.4f})")
    return best_k


def reduce_dimensions_umap(
    vectors: np.ndarray,
    n_components: int = 50,
    n_neighbors: int = 15,
    min_dist: float = 0.1,
    metric: str = 'cosine',
    random_state: int = 42,
    verbose: bool = True
) -> np.ndarray:
    """UMAP 降维，保留语义结构"""
    if verbose:
        print(f"UMAP 降维: {vectors.shape[1]} → {n_components} 维 (n_neighbors={n_neighbors}, metric={metric})")

    reducer = umap.UMAP(
        n_components=n_components,
        n_neighbors=n_neighbors,
        min_dist=min_dist,
        metric=metric,
        random_state=random_state,
        verbose=verbose
    )

    reduced = reducer.fit_transform(vectors)

    if verbose:
        print(f"降维完成: {reduced.shape}")

    return reduced


def cluster_steps(
    vector_store: LanceVectorStore,
    algorithm: ClusteringAlgorithm,
    umap_config: Optional[Dict] = None,
    verbose: bool = True
) -> ClusterResult:
    """从 LanceDB 读取向量，可选 UMAP 降维，聚类，回写标签"""
    arrow_table = vector_store.table.to_arrow()
    chain_ids = arrow_table.column("chain_id").to_pylist()
    vectors = np.array(arrow_table.column("vector").to_pylist(), dtype=np.float32)

    if len(chain_ids) == 0:
        raise ValueError("No vectors in LanceDB — nothing to cluster")

    if verbose:
        print(f"Loaded {len(chain_ids)} vectors from LanceDB, dim={vectors.shape[1]}")

    # 1. UMAP 降维（可选）
    clustering_vectors = vectors
    if umap_config and umap_config.get("enabled", False):
        clustering_vectors = reduce_dimensions_umap(
            vectors,
            n_components=umap_config.get("n_components", 50),
            n_neighbors=umap_config.get("n_neighbors", 15),
            min_dist=umap_config.get("min_dist", 0.1),
            metric=umap_config.get("metric", "cosine"),
            verbose=verbose
        )

    # 2. 执行聚类
    labels = algorithm.fit(clustering_vectors)
    centers = algorithm.get_cluster_centers()

    # 3. 计算评估指标（用降维后的向量）
    metrics = evaluate_clustering(clustering_vectors, labels)

    # 4. 回写 LanceDB
    updates = [(chain_id, {"cluster_id": int(label)})
               for chain_id, label in zip(chain_ids, labels)]
    vector_store.batch_update_metadata(updates)

    # 5. 打印统计
    if verbose:
        print(f"\n{'='*60}")
        print(f"Clustering complete:")
        print(f"  Algorithm: {algorithm.__class__.__name__}")
        print(f"  Input dim: {vectors.shape[1]}" + (f" → {clustering_vectors.shape[1]} (UMAP)" if umap_config and umap_config.get("enabled") else ""))
        print(f"  Clusters: {algorithm.n_clusters}")
        print(f"  Noise points: {metrics.get('n_noise', 0)} ({metrics.get('noise_ratio', 0)*100:.1f}%)")
        if "silhouette" in metrics:
            print(f"  Silhouette score: {metrics['silhouette']:.4f} (sampled {metrics.get('silhouette_sample_size', '?')})")
            print(f"  Calinski-Harabasz: {metrics.get('calinski_harabasz', 0):.1f}")
            print(f"  Davies-Bouldin: {metrics.get('davies_bouldin', 0):.4f}")
        if "cluster_size_median" in metrics:
            print(f"  Cluster sizes: min={metrics['cluster_size_min']}, median={metrics['cluster_size_median']:.0f}, max={metrics['cluster_size_max']}, mean={metrics['cluster_size_mean']:.0f}")
        print(f"\n  Top 20 largest clusters:")
        size_dist = sorted(Counter(labels).items(), key=lambda x: -x[1])
        for cluster_id, count in size_dist[:20]:
            label_str = "noise" if cluster_id == -1 else f"C{cluster_id}"
            print(f"    {label_str}: {count} chains")
        print(f"{'='*60}")

    return ClusterResult(
        n_clusters=algorithm.n_clusters,
        labels=labels,
        step_ids=chain_ids,
        centers=centers,
        metrics=metrics
    )


def save_cluster_results(result: ClusterResult, output_dir: Path) -> None:
    """保存聚类结果到文件"""
    output_dir.mkdir(parents=True, exist_ok=True)

    # cluster_labels.json: {chain_id: cluster_id}
    labels_path = output_dir / "cluster_labels.json"
    labels_map = {cid: int(label) for cid, label in zip(result.step_ids, result.labels)}
    with open(labels_path, 'w') as f:
        json.dump(labels_map, f, indent=2)

    # cluster_stats.json: 统计信息
    stats_path = output_dir / "cluster_stats.json"
    cluster_sizes = Counter(int(l) for l in result.labels)
    stats = {
        "n_clusters": result.n_clusters,
        "metrics": result.metrics,
        "cluster_sizes": {str(k): v for k, v in sorted(cluster_sizes.items())},
    }
    with open(stats_path, 'w') as f:
        json.dump(stats, f, indent=2)

    # cluster_centers.npy: 聚类中心向量
    if result.centers is not None:
        centers_path = output_dir / "cluster_centers.npy"
        np.save(centers_path, result.centers)

    print(f"Saved cluster results to {output_dir}")
