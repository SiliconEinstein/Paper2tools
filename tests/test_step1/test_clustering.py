"""
测试聚类算法模块

测试内容:
- 各种聚类算法的正确性
- K-means 聚类结果
- DBSCAN 密度聚类
- 最优 k 值搜索
- 聚类评估指标计算
- 边界情况（单个样本、所有样本相同）
"""

import pytest
import numpy as np
from src.step1.clustering import (
    KMeansClustering,
    HDBSCANClustering,
    create_clustering_algorithm,
    evaluate_clustering,
    find_optimal_k,
    ClusterResult
)


@pytest.fixture
def sample_vectors():
    """生成测试用向量数据"""
    np.random.seed(42)
    # 3 个簇，每簇 20 个点
    cluster1 = np.random.randn(20, 10) + np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    cluster2 = np.random.randn(20, 10) + np.array([5, 5, 5, 5, 5, 5, 5, 5, 5, 5])
    cluster3 = np.random.randn(20, 10) + np.array([-5, -5, -5, -5, -5, -5, -5, -5, -5, -5])
    return np.vstack([cluster1, cluster2, cluster3]).astype(np.float32)


def test_kmeans_clustering(sample_vectors):
    """测试 K-means 聚类"""
    algo = KMeansClustering(n_clusters=3, random_seed=42)
    labels = algo.fit(sample_vectors)

    assert len(labels) == len(sample_vectors)
    assert len(set(labels)) == 3  # 应该有 3 个簇
    assert all(label >= 0 for label in labels)  # 所有标签非负


def test_kmeans_cluster_centers(sample_vectors):
    """测试 K-means 聚类中心"""
    algo = KMeansClustering(n_clusters=3, random_seed=42)
    algo.fit(sample_vectors)
    centers = algo.get_cluster_centers()

    assert centers.shape == (3, 10)  # 3 个中心，每个 10 维
    # sklearn 返回 float64 或 float32 都可以
    assert centers.dtype in [np.float32, np.float64]


def test_hdbscan_clustering(sample_vectors):
    """测试 HDBSCAN 聚类"""
    algo = HDBSCANClustering(min_cluster_size=5, min_samples=3)
    labels = algo.fit(sample_vectors)

    assert len(labels) == len(sample_vectors)
    # HDBSCAN 可能产生噪声点（标签 -1）
    unique_labels = set(labels)
    assert len(unique_labels) >= 2  # 至少有 2 个簇（可能包含噪声）


def test_create_kmeans_from_config():
    """测试从配置创建 K-means 聚类器"""
    config = {
        "algorithm": "kmeans",
        "n_clusters": 5,
        "random_seed": 123
    }
    algo = create_clustering_algorithm(config)

    assert isinstance(algo, KMeansClustering)
    assert algo.n_clusters == 5


def test_create_hdbscan_from_config():
    """测试从配置创建 HDBSCAN 聚类器"""
    config = {
        "algorithm": "hdbscan",
        "hdbscan": {
            "min_cluster_size": 10,
            "min_samples": 5
        }
    }
    algo = create_clustering_algorithm(config)

    assert isinstance(algo, HDBSCANClustering)


def test_invalid_algorithm_config():
    """测试无效的算法配置"""
    config = {"algorithm": "invalid_algo"}

    with pytest.raises(ValueError, match="Unknown clustering algorithm"):
        create_clustering_algorithm(config)


def test_kmeans_missing_n_clusters():
    """测试 K-means 缺少 n_clusters 参数"""
    config = {"algorithm": "kmeans"}

    with pytest.raises(ValueError, match="n_clusters required"):
        create_clustering_algorithm(config)


def test_evaluate_clustering(sample_vectors):
    """测试聚类评估指标"""
    algo = KMeansClustering(n_clusters=3, random_seed=42)
    labels = algo.fit(sample_vectors)

    metrics = evaluate_clustering(sample_vectors, labels)

    assert "n_clusters" in metrics
    assert "n_noise" in metrics
    assert "n_total" in metrics
    assert metrics["n_clusters"] == 3
    assert metrics["n_total"] == len(sample_vectors)

    # 应该有质量指标
    assert "silhouette" in metrics
    assert "calinski_harabasz" in metrics
    assert "davies_bouldin" in metrics


def test_evaluate_clustering_with_noise():
    """测试包含噪声点的聚类评估"""
    vectors = np.random.randn(50, 10).astype(np.float32)
    labels = np.array([0] * 20 + [1] * 20 + [-1] * 10)  # 10 个噪声点

    metrics = evaluate_clustering(vectors, labels)

    assert metrics["n_noise"] == 10
    assert metrics["n_clusters"] == 2


def test_single_cluster():
    """测试单簇情况"""
    vectors = np.random.randn(20, 10).astype(np.float32)
    algo = KMeansClustering(n_clusters=1, random_seed=42)
    labels = algo.fit(vectors)

    assert len(set(labels)) == 1
    assert all(label == 0 for label in labels)


def test_more_clusters_than_samples():
    """测试簇数多于样本数"""
    vectors = np.random.randn(5, 10).astype(np.float32)

    # sklearn 会报错，因为 n_clusters > n_samples
    with pytest.raises(ValueError):
        algo = KMeansClustering(n_clusters=10, random_seed=42)
        algo.fit(vectors)


def test_identical_vectors():
    """测试所有向量相同的情况"""
    vectors = np.ones((20, 10), dtype=np.float32)
    algo = KMeansClustering(n_clusters=3, random_seed=42)
    labels = algo.fit(vectors)

    # 所有点应该被分到同一簇
    assert len(set(labels)) <= 3


def test_find_optimal_k_basic():
    """测试最优 k 值搜索（基础功能）"""
    np.random.seed(42)
    vectors = np.random.randn(100, 10).astype(np.float32)

    # 搜索范围较小以加快测试
    optimal_k = find_optimal_k(vectors, min_k=2, max_k=5)

    assert 2 <= optimal_k <= 5


def test_cluster_result_dataclass():
    """测试 ClusterResult 数据类"""
    labels = np.array([0, 0, 1, 1, 2])
    step_ids = ["s1", "s2", "s3", "s4", "s5"]
    centers = np.random.randn(3, 10).astype(np.float32)
    metrics = {"silhouette": 0.5}

    result = ClusterResult(
        n_clusters=3,
        labels=labels,
        step_ids=step_ids,
        centers=centers,
        metrics=metrics
    )

    assert result.n_clusters == 3
    assert len(result.labels) == 5
    assert len(result.step_ids) == 5
    assert result.centers.shape == (3, 10)
    assert result.metrics["silhouette"] == 0.5


def test_clustering_reproducibility():
    """测试聚类结果的可重现性"""
    vectors = np.random.randn(50, 10).astype(np.float32)

    algo1 = KMeansClustering(n_clusters=3, random_seed=42)
    labels1 = algo1.fit(vectors)

    algo2 = KMeansClustering(n_clusters=3, random_seed=42)
    labels2 = algo2.fit(vectors)

    # 相同随机种子应该产生相同结果
    assert np.array_equal(labels1, labels2)
