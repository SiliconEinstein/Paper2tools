"""
聚类主流程：工厂、评估、Lance 读向量、cluster_steps、保存结果。
"""

import json
import gc
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score, calinski_harabasz_score, davies_bouldin_score
import umap

from ...db import LanceVectorStore
from .base import ClusterResult, ClusteringAlgorithm
from .kmeans_hdbscan import KMeansClustering, HDBSCANClustering


def create_clustering_algorithm(config: Dict) -> ClusteringAlgorithm:
    """工厂函数，根据配置创建聚类器。

    clustering.device:
        - cpu（默认）: sklearn MiniBatchKMeans / KMeans；hdbscan 为 CPU（hdbscan 库，支持 cosine 等度量）
        - gpu: KMeans 用 cuML；HDBSCAN 用 cuML HDBSCAN（仅 euclidean；cosine 会先 L2 归一化再聚类）
        - auto: KMeans / HDBSCAN 在能加载对应 cuML 实现时用 GPU，否则 CPU
    """
    algo = config["algorithm"]
    device = str(config.get("device", "cpu")).lower().strip()

    if algo == "kmeans":
        k = config.get("n_clusters")
        if k is None:
            raise ValueError("n_clusters required for kmeans")

        use_gpu = False
        if device == "gpu":
            use_gpu = True
        elif device == "auto":
            from .gpu import is_cuml_kmeans_available

            use_gpu = is_cuml_kmeans_available()
            if use_gpu:
                print("[clustering] device=auto → 使用 RAPIDS cuML MiniBatchKMeans (GPU)")
            else:
                print("[clustering] device=auto → cuML 不可用，使用 sklearn (CPU)")

        if use_gpu:
            from .gpu import CumlMiniBatchKMeansClustering, is_cuml_kmeans_available

            if not is_cuml_kmeans_available():
                raise RuntimeError(
                    "clustering.device=gpu 但未安装或无法加载 RAPIDS cuML。"
                    "请安装 cuML（见 requirements-gpu.txt 说明）或改为 device: cpu / auto。"
                )
            if device == "gpu":
                print("[clustering] device=gpu → RAPIDS cuML MiniBatchKMeans (GPU)")
            return CumlMiniBatchKMeansClustering(
                n_clusters=k,
                random_seed=int(config.get("random_seed", 42)),
                batch_size=int(config.get("batch_size", 10000)),
                max_iter=int(config.get("max_iter", 300)),
            )

        return KMeansClustering(
            n_clusters=k,
            random_seed=config.get("random_seed", 42),
            mini_batch=config.get("mini_batch", True),
            batch_size=int(config.get("batch_size", 10000)),
        )
    elif algo == "hdbscan":
        from .gpu import CumlHDBSCANClustering, is_cuml_hdbscan_available

        hdb_cfg = config["hdbscan"]
        metric = (hdb_cfg.get("metric") or "euclidean").lower().strip()
        cuml_ok = is_cuml_hdbscan_available()
        use_cuml = False
        if device == "gpu":
            if not cuml_ok:
                raise RuntimeError(
                    "clustering.device=gpu 且 algorithm=hdbscan，但未安装或无法加载 "
                    "cuml.cluster.hdbscan.HDBSCAN。请按 requirements-gpu.txt 安装 RAPIDS cuML，"
                    "或改为 device: cpu / auto。"
                )
            if metric not in ("euclidean", "l2", "cosine", "angular"):
                raise RuntimeError(
                    f"cuML HDBSCAN 仅支持欧氏距离；metric={metric!r} 请改用 device: cpu。"
                )
            use_cuml = True
        elif device == "auto" and cuml_ok and metric in ("euclidean", "l2", "cosine", "angular"):
            use_cuml = True
            print("[clustering] device=auto → 使用 RAPIDS cuML HDBSCAN (GPU)")

        if use_cuml:
            if metric in ("cosine", "angular"):
                print(
                    "[clustering] 提示: cuML HDBSCAN 仅 euclidean；"
                    "metric=cosine 时对向量做 L2 归一化后再聚类，质心在原始向量上计算。"
                )
            return CumlHDBSCANClustering(
                min_cluster_size=hdb_cfg["min_cluster_size"],
                min_samples=hdb_cfg.get("min_samples"),
                metric=metric,
                cluster_selection_epsilon=hdb_cfg.get("cluster_selection_epsilon", 0.0),
                cluster_selection_method=hdb_cfg.get("cluster_selection_method", "eom"),
                build_algo=str(hdb_cfg.get("cuml_build_algo", "nn_descent")),
            )

        if device == "auto" and not cuml_ok:
            print("[clustering] device=auto → cuML HDBSCAN 不可用，使用 CPU hdbscan")
        return HDBSCANClustering(
            min_cluster_size=hdb_cfg["min_cluster_size"],
            min_samples=hdb_cfg["min_samples"],
            metric=hdb_cfg.get("metric", "euclidean"),
            cluster_selection_epsilon=hdb_cfg.get("cluster_selection_epsilon", 0.0),
            cluster_selection_method=hdb_cfg.get("cluster_selection_method", "eom"),
        )
    elif algo == "agglomerative":
        from .agglomerative import AgglomerativeConstrainedClustering, agglomerative_config_from_clustering

        if device in ("gpu", "auto"):
            print(
                "[clustering] 提示: agglomerative 当前为 CPU 实现；"
                "device=gpu/auto 不切换该算法（两阶段中微簇仍用 sklearn MiniBatchKMeans）。"
            )
        return AgglomerativeConstrainedClustering(
            agglomerative_config_from_clustering(config),
            random_seed=int(config.get("random_seed", 42)),
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

    cluster_sizes = Counter(int(l) for l in valid_labels)
    sizes = sorted(cluster_sizes.values())
    if sizes:
        metrics["cluster_size_min"] = sizes[0]
        metrics["cluster_size_max"] = sizes[-1]
        metrics["cluster_size_median"] = float(np.median(sizes))
        metrics["cluster_size_mean"] = float(np.mean(sizes))

    if n_valid_clusters >= 2:
        n = len(valid_vectors)
        if n > sample_size:
            idx = np.random.RandomState(42).choice(n, sample_size, replace=False)
            metrics["silhouette"] = float(silhouette_score(valid_vectors[idx], valid_labels[idx]))
            metrics["silhouette_sample_size"] = sample_size
        else:
            metrics["silhouette"] = float(silhouette_score(valid_vectors, valid_labels))
            metrics["silhouette_sample_size"] = n

        metrics["calinski_harabasz"] = float(calinski_harabasz_score(valid_vectors, valid_labels))
        if n_valid_clusters <= 5000:
            metrics["davies_bouldin"] = float(davies_bouldin_score(valid_vectors, valid_labels))
        else:
            metrics["davies_bouldin"] = float("nan")
            metrics["davies_bouldin_skipped"] = True
            metrics["davies_bouldin_skip_reason"] = "n_clusters>5000"

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


def _arrow_list_vector_column_to_numpy(vec_column: pa.Array | pa.ChunkedArray) -> np.ndarray:
    """将 Lance/PyArrow 的 list<float32> 列转为 (n, dim) float32，避免逐行 as_py。

    假定每行向量长度一致（固定维 embedding）；否则走慢路径或报错。
    """
    if isinstance(vec_column, pa.ChunkedArray):
        vec_column = vec_column.combine_chunks()
    n = len(vec_column)
    if n == 0:
        return np.zeros((0, 0), dtype=np.float32)
    offsets = vec_column.offsets.to_numpy()
    dims = np.diff(offsets.astype(np.int64))
    d0 = int(dims[0])
    if int(dims.min()) != int(dims.max()):
        raise ValueError(
            "向量行长度不一致，无法使用 list_flatten 快速加载；请检查 Lance 表中 vector 列。"
        )
    flat = pc.list_flatten(vec_column)
    buf = flat.to_numpy(zero_copy_only=False)
    if buf.dtype != np.float32:
        buf = buf.astype(np.float32, copy=False)
    return np.ascontiguousarray(buf.reshape(n, d0))


def cluster_steps(
    vector_store: LanceVectorStore,
    algorithm: ClusteringAlgorithm,
    domain: Optional[str] = None,
    umap_config: Optional[Dict] = None,
    verbose: bool = True,
    cosine_metrics_config: Optional[Dict] = None,
) -> ClusterResult:
    """从 LanceDB 读取向量，可选 UMAP 降维，聚类"""
    if verbose:
        if domain:
            print(f"Loading vectors from LanceDB (domain={domain}, chain_id + vector only)...")
        else:
            print("Loading vectors from LanceDB (chain_id + vector only)...")

    t0 = time.monotonic()
    search = vector_store.table.search()
    if domain:
        search = search.where(f"domain = '{domain}'")
    arrow_table = search.select(["chain_id", "vector"]).limit(999999999).to_arrow()
    t_arrow = time.monotonic()

    chain_ids = arrow_table.column("chain_id").to_pylist()
    t_ids = time.monotonic()

    vectors = _arrow_list_vector_column_to_numpy(arrow_table.column("vector"))
    del arrow_table
    gc.collect()
    t_done = time.monotonic()

    if verbose:
        print(
            f"  Lance→内存: to_arrow {t_arrow - t0:.1f}s, chain_id 列 {t_ids - t_arrow:.1f}s, "
            f"向量展平 {t_done - t_ids:.1f}s"
        )

    if len(chain_ids) == 0:
        raise ValueError("No vectors in LanceDB — nothing to cluster")

    if verbose:
        mem_mb = vectors.nbytes / 1024 / 1024
        print(f"Loaded {len(chain_ids)} vectors, dim={vectors.shape[1]}, mem={mem_mb:.0f}MB")

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

    labels = algorithm.fit(clustering_vectors)
    centers = algorithm.get_cluster_centers()

    metrics = evaluate_clustering(clustering_vectors, labels)

    cm_cfg = cosine_metrics_config or {}
    if cm_cfg.get("enabled", True):
        from .cosine_metrics import (
            compute_cosine_quality_metrics,
            merge_cosine_metrics_into_metrics,
        )

        embed_for_cosine = (
            vectors
            if (umap_config and umap_config.get("enabled"))
            else clustering_vectors
        )
        cq = compute_cosine_quality_metrics(
            embed_for_cosine,
            labels,
            subsample_n=int(cm_cfg.get("subsample_n", 20000)),
            max_points_per_cluster=int(cm_cfg.get("max_points_per_cluster", 32)),
            cosine_split_threshold=float(cm_cfg.get("cosine_split_threshold", 0.85)),
            sim_block_rows=int(cm_cfg.get("sim_block_rows", 256)),
            random_state=int(cm_cfg.get("random_state", 42)),
        )
        merge_cosine_metrics_into_metrics(metrics, cq)
        if verbose and cq.get("skipped") is False:
            isp = cq.get("intra_sim_p50")
            msp = cq.get("min_sim_p50")
            hsr = cq.get("high_sim_split_rate")
            thr = float(cm_cfg.get("cosine_split_threshold", 0.85))
            print(
                f"  Cosine quality (subsample n={cq.get('subsample_n')}): "
                f"intra_sim P50={isp if isp is None else f'{isp:.4f}'}, "
                f"min_sim P50={msp if msp is None else f'{msp:.4f}'}, "
                f"high-sim split rate={hsr if hsr is None else f'{hsr:.4f}'} "
                f"(pairs≥{thr}: {cq.get('high_sim_pair_count')})"
            )
        elif verbose and cq.get("skipped"):
            print(f"  Cosine quality: skipped ({cq.get('reason', '')})")

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

    labels_path = output_dir / "cluster_labels.json"
    labels_map = {cid: int(label) for cid, label in zip(result.step_ids, result.labels)}
    with open(labels_path, 'w') as f:
        json.dump(labels_map, f, indent=2)

    stats_path = output_dir / "cluster_stats.json"
    cluster_sizes = Counter(int(l) for l in result.labels)
    stats = {
        "n_clusters": result.n_clusters,
        "metrics": result.metrics,
        "cluster_sizes": {str(k): v for k, v in sorted(cluster_sizes.items())},
    }
    with open(stats_path, 'w') as f:
        json.dump(stats, f, indent=2)

    if result.centers is not None:
        centers_path = output_dir / "cluster_centers.npy"
        np.save(centers_path, result.centers)

    print(f"Saved cluster results to {output_dir}")
