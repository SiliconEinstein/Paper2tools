"""思维链相似度：向量统计与分组（不连 Lance / 不调 LLM）。"""

import numpy as np

from src.step4.chain_similarity import (
    group_chains_by_cluster,
    pairwise_cosine_upper_triangle,
    summarize_similarities,
)


def test_pairwise_cosine_orthogonal():
    v = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float64)
    s = pairwise_cosine_upper_triangle(v)
    assert s.size == 1
    assert abs(float(s[0])) < 1e-6


def test_pairwise_cosine_parallel():
    v = np.array([[1.0, 0.0], [2.0, 0.0]], dtype=np.float64)
    s = pairwise_cosine_upper_triangle(v)
    assert abs(float(s[0]) - 1.0) < 1e-6


def test_summarize_empty():
    st = summarize_similarities(np.array([], dtype=np.float64))
    assert st["n_pairs"] == 0
    assert st["max"] is None


def test_group_chains_by_cluster():
    rows = [
        {"chain_id": "a", "cluster_id": 2, "distance": 0.5},
        {"chain_id": "b", "cluster_id": 1, "distance": 0.1},
        {"chain_id": "c", "cluster_id": 1, "distance": 0.2},
    ]
    g = group_chains_by_cluster(rows)
    assert set(g.keys()) == {1, 2}
    assert [x["chain_id"] for x in g[1]] == ["b", "c"]
