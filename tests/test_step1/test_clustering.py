"""
测试聚类算法模块

测试内容:
- Agglomerative 约束聚类算法
- 两阶段聚类（大数据集）
- 子组构建逻辑
"""

import pytest
import numpy as np
from src.step1.clustering import AgglomerativeConstrainedClustering, build_sub_groups


@pytest.fixture
def sample_vectors():
    """生成测试用向量数据"""
    np.random.seed(42)
    # 3 个簇，每簇 20 个点
    cluster1 = np.random.randn(20, 10) + np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    cluster2 = np.random.randn(20, 10) + np.array([5, 5, 5, 5, 5, 5, 5, 5, 5, 5])
    cluster3 = np.random.randn(20, 10) + np.array([-5, -5, -5, -5, -5, -5, -5, -5, -5, -5])
    return np.vstack([cluster1, cluster2, cluster3]).astype(np.float32)


def test_agglomerative_basic(sample_vectors):
    """测试 Agglomerative 聚类基础功能"""
    algo = AgglomerativeConstrainedClustering(
        {"max_size": 30, "min_pair_sim": 0.5},
        random_seed=42
    )
    labels = algo.fit(sample_vectors)

    assert len(labels) == len(sample_vectors)
    assert algo.n_clusters >= 1
    assert all(label >= 0 for label in labels)


def test_agglomerative_cluster_centers(sample_vectors):
    """测试聚类中心计算"""
    algo = AgglomerativeConstrainedClustering(
        {"max_size": 30, "min_pair_sim": 0.5},
        random_seed=42
    )
    algo.fit(sample_vectors)
    centers = algo.get_cluster_centers()

    assert centers is not None
    assert centers.shape[0] == algo.n_clusters
    assert centers.shape[1] == sample_vectors.shape[1]


def test_agglomerative_from_config():
    """测试从配置创建 Agglomerative 聚类器"""
    from src.step1.cluster.pipeline import create_clustering_algorithm

    config = {
        "algorithm": "agglomerative",
        "agglomerative": {"max_size": 80, "min_pair_sim": 0.2},
    }
    algo = create_clustering_algorithm(config)
    assert isinstance(algo, AgglomerativeConstrainedClustering)


def test_build_sub_groups_small():
    """测试子组构建（小数据集）"""
    np.random.seed(1)
    n, d = 24, 6
    X = np.random.randn(n, d).astype(np.float32)
    labels, g = build_sub_groups(X, max_size=12, min_pair_sim=0.15, weights=None)
    assert labels.shape == (n,)
    assert 1 <= g <= n
    assert len(np.unique(labels)) == g


def test_agglomerative_two_stage_path():
    """测试两阶段聚类路径（大数据集）"""
    np.random.seed(2)
    n, d = 800, 8
    X = np.random.randn(n, d).astype(np.float32)
    algo = AgglomerativeConstrainedClustering(
        {
            "max_size": 100,
            "min_pair_sim": 0.1,
            "max_n_exact": 200,
            "micro_k": 40,
            "micro_batch_size": 256,
            "micro_max_iter": 30,
        },
        random_seed=42,
    )
    labels = algo.fit(X)
    assert labels.shape == (n,)
    assert algo.n_clusters >= 1
    c = algo.get_cluster_centers()
    assert c is not None and c.shape[1] == d


def test_agglomerative_max_size_constraint():
    """测试最大簇大小约束"""
    np.random.seed(3)
    n, d = 100, 5
    X = np.random.randn(n, d).astype(np.float32)

    max_size = 20
    algo = AgglomerativeConstrainedClustering(
        {"max_size": max_size, "min_pair_sim": 0.3},
        random_seed=42
    )
    labels = algo.fit(X)

    # 检查每个簇的大小
    from collections import Counter
    cluster_sizes = Counter(labels)
    for size in cluster_sizes.values():
        assert size <= max_size, f"Cluster size {size} exceeds max_size {max_size}"


def test_agglomerative_min_pair_sim_constraint():
    """测试最小相似度约束"""
    np.random.seed(4)
    # 创建两个明显分离的簇
    cluster1 = np.random.randn(30, 10) + np.array([0] * 10)
    cluster2 = np.random.randn(30, 10) + np.array([10] * 10)
    X = np.vstack([cluster1, cluster2]).astype(np.float32)

    # 使用较高的相似度阈值，应该产生至少 2 个簇
    algo = AgglomerativeConstrainedClustering(
        {"max_size": 100, "min_pair_sim": 0.8},
        random_seed=42
    )
    labels = algo.fit(X)

    assert algo.n_clusters >= 2, "Should produce at least 2 clusters for well-separated data"


def test_clustering_reproducibility():
    """测试聚类结果的可重现性"""
    np.random.seed(5)
    vectors = np.random.randn(50, 10).astype(np.float32)

    algo1 = AgglomerativeConstrainedClustering(
        {"max_size": 30, "min_pair_sim": 0.5},
        random_seed=42
    )
    labels1 = algo1.fit(vectors)

    algo2 = AgglomerativeConstrainedClustering(
        {"max_size": 30, "min_pair_sim": 0.5},
        random_seed=42
    )
    labels2 = algo2.fit(vectors)

    # 相同随机种子应该产生相同结果
    assert np.array_equal(labels1, labels2)
