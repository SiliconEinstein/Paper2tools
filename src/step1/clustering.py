"""
聚类对外唯一入口：请从本模块导入所有公开 API。

实现代码位于同目录下的 ``cluster/`` 子包内。
"""

from .cluster.base import ClusterResult, ClusteringAlgorithm
from .cluster.kmeans_hdbscan import KMeansClustering, HDBSCANClustering
from .cluster.pipeline import (
    create_clustering_algorithm,
    cluster_steps,
    save_cluster_results,
    evaluate_clustering,
    find_optimal_k,
    reduce_dimensions_umap,
)
from .cluster.selector import select_top_clusters, save_selection, parse_selection_config
from .cluster.agglomerative import (
    AgglomerativeConstrainedClustering,
    build_sub_groups,
    agglomerative_config_from_clustering,
)
from .cluster.cosine_metrics import (
    compute_cosine_quality_metrics,
    merge_cosine_metrics_into_metrics,
)
from .cluster.gpu import (
    is_cuml_kmeans_available,
    is_cuml_hdbscan_available,
    CumlMiniBatchKMeansClustering,
    CumlHDBSCANClustering,
)

__all__ = [
    "ClusterResult",
    "ClusteringAlgorithm",
    "KMeansClustering",
    "HDBSCANClustering",
    "AgglomerativeConstrainedClustering",
    "build_sub_groups",
    "agglomerative_config_from_clustering",
    "CumlMiniBatchKMeansClustering",
    "CumlHDBSCANClustering",
    "is_cuml_kmeans_available",
    "is_cuml_hdbscan_available",
    "create_clustering_algorithm",
    "cluster_steps",
    "save_cluster_results",
    "evaluate_clustering",
    "find_optimal_k",
    "reduce_dimensions_umap",
    "select_top_clusters",
    "save_selection",
    "parse_selection_config",
    "compute_cosine_quality_metrics",
    "merge_cosine_metrics_into_metrics",
]
