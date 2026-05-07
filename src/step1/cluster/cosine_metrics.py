"""
基于余弦相似度的聚类质量指标（与 embedding 空间语义一致）：

- intra_sim：每个簇内所有点对的平均余弦相似度；再对所有簇取 P50（中位数）。
- min_sim：每个簇内点对余弦相似度的最小值（最远的 pair）；再对所有簇取 P50。
- high_sim_split_rate：在余弦相似度 >= 阈值的点对中，被分到不同簇的比例。

大规模数据在固定子样本上估计（默认 20000 条向量），避免 O(N^2) 全量。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Tuple

import numpy as np
from sklearn.preprocessing import normalize


def _jsonable(x: Any) -> Any:
    if isinstance(x, float) and (np.isnan(x) or np.isinf(x)):
        return None
    if isinstance(x, dict):
        return {k: _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (np.floating, np.float32, np.float64)):
        return float(x)
    if isinstance(x, (np.integer, np.int32, np.int64)):
        return int(x)
    if isinstance(x, np.ndarray):
        return x.tolist()
    return x


def compute_cosine_quality_metrics(
    vectors: np.ndarray,
    labels: np.ndarray,
    noise_label: int = -1,
    subsample_n: int = 20000,
    max_points_per_cluster: int = 32,
    cosine_split_threshold: float = 0.85,
    sim_block_rows: int = 256,
    random_state: int = 42,
) -> Dict[str, Any]:
    """
    在 (vectors, labels) 上计算余弦质量指标；若 rows > subsample_n 则先无放回随机子采样。

    Returns
    -------
    dict
        含 intra_sim_p50、min_sim_p50、high_sim_split_rate 及采样说明字段。
    """
    rng = np.random.RandomState(random_state)
    labels = np.asarray(labels).astype(np.int64, copy=False)
    vectors = np.asarray(vectors, dtype=np.float32, copy=False)

    valid = labels != noise_label
    X = vectors[valid]
    y = labels[valid]
    n = len(y)
    if n < 2:
        return _jsonable(
            {
                "enabled": True,
                "skipped": True,
                "reason": "fewer than 2 non-noise points",
            }
        )

    if n > subsample_n:
        idx = rng.choice(n, size=subsample_n, replace=False)
        X = X[idx]
        y = y[idx]
        n = subsample_n

    Xn = normalize(X, norm="l2", axis=1, copy=True)

    # ── 簇内 pairwise：每簇最多 max_points_per_cluster 个点 ──
    by_c: Dict[int, List[int]] = defaultdict(list)
    for i, c in enumerate(y):
        by_c[int(c)].append(i)

    intra_per_c: List[float] = []
    min_per_c: List[float] = []
    clusters_with_pairs = 0

    for c, inds in by_c.items():
        if len(inds) < 2:
            continue
        inds = np.array(inds, dtype=np.int64)
        if len(inds) > max_points_per_cluster:
            inds = rng.choice(inds, size=max_points_per_cluster, replace=False)
        V = Xn[inds]
        g = V @ V.T
        tri = np.triu_indices(len(V), k=1)
        sims = g[tri]
        if sims.size == 0:
            continue
        clusters_with_pairs += 1
        intra_per_c.append(float(np.mean(sims)))
        min_per_c.append(float(np.min(sims)))

    intra_sim_p50 = float(np.median(intra_per_c)) if intra_per_c else float("nan")
    min_sim_p50 = float(np.median(min_per_c)) if min_per_c else float("nan")

    # ── 高相似 split rate：分块上三角，避免整块 n×n 矩阵 ──
    high_sim_total = 0
    high_sim_split = 0
    for i0 in range(0, n, sim_block_rows):
        i1 = min(i0 + sim_block_rows, n)
        block = Xn[i0:i1] @ Xn.T  # (i1-i0) x n
        for bi, gi in enumerate(range(i0, i1)):
            row = block[bi, gi + 1 :]
            if row.size == 0:
                continue
            mask = row >= cosine_split_threshold
            if not np.any(mask):
                continue
            j_global = np.arange(gi + 1, n, dtype=np.int64)[mask]
            same = y[j_global] != y[gi]
            high_sim_total += int(mask.sum())
            high_sim_split += int(same.sum())

    split_rate = (
        float(high_sim_split) / float(high_sim_total) if high_sim_total > 0 else float("nan")
    )

    return _jsonable(
        {
            "enabled": True,
            "skipped": False,
            "subsample_n": int(n),
            "subsample_seed": int(random_state),
            "max_points_per_cluster": int(max_points_per_cluster),
            "cosine_split_threshold": float(cosine_split_threshold),
            "clusters_with_pairwise_estimate": int(clusters_with_pairs),
            "intra_sim_p50": intra_sim_p50,
            "min_sim_p50": min_sim_p50,
            "intra_sim_per_cluster_mean": float(np.mean(intra_per_c)) if intra_per_c else float("nan"),
            "min_sim_per_cluster_mean": float(np.mean(min_per_c)) if min_per_c else float("nan"),
            "high_sim_pair_count": int(high_sim_total),
            "high_sim_split_count": int(high_sim_split),
            "high_sim_split_rate": split_rate,
            "high_sim_same_cluster_rate": float(1.0 - split_rate)
            if not np.isnan(split_rate)
            else float("nan"),
        }
    )


def merge_cosine_metrics_into_metrics(
    metrics: Dict[str, Any], cosine_block: Dict[str, Any]
) -> None:
    """将余弦指标并入 evaluate_clustering 的 metrics（嵌套键 cosine_quality）。"""
    metrics["cosine_quality"] = cosine_block
