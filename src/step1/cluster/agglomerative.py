"""
受约束的凝聚聚类（complete-linkage + max_size + min_pair_sim），
参考 build_sub_groups：归一化余弦相似度、最大堆合并、合并后 inter = min(sim(keeper,ck), sim(victim,ck))。

大规模样本（如 5 万）：全量 O(n^2) 相似度矩阵不可行，采用两阶段：
  1) MiniBatchKMeans 得到 micro_k 个微簇及质心、每簇样本数；
  2) 在质心上做受约束合并（权重=微簇内点数），再将每条样本映射到超簇标签。
"""

from __future__ import annotations

import heapq
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
from sklearn.cluster import MiniBatchKMeans
from sklearn.preprocessing import normalize

from .base import ClusteringAlgorithm


def _pair_key(i: int, j: int) -> Tuple[int, int]:
    return (i, j) if i < j else (j, i)


def _min_inter_from_matrix(a: Set[int], b: Set[int], sim: np.ndarray) -> float:
    """complete-link: 两组点之间的最小余弦相似度。"""
    best = 1.0
    for ia in a:
        row = sim[ia]
        for ib in b:
            v = float(row[ib])
            if v < best:
                best = v
    return best


def build_sub_groups(
    member_vecs: np.ndarray,
    max_size: int = 50,
    min_pair_sim: float = 0.45,
    weights: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, int]:
    """
    对 member_vecs 的每一行（样本）做受约束凝聚聚类。

    Parameters
    ----------
    member_vecs : (n, d) float32/float64
    max_size : 合并后簇内权重之和上限（权重为 None 时即点数）
    min_pair_sim : 可合并的最小簇间相似度（余弦，已 L2 归一化后点积）
    weights : (n,) 非负整数，可为 None 表示全 1

    Returns
    -------
    labels : (n,) int32，取值 0..G-1
    n_clusters : G
    """
    n = int(member_vecs.shape[0])
    if n == 0:
        raise ValueError("build_sub_groups: empty member_vecs")
    if n == 1:
        return np.zeros(1, dtype=np.int32), 1

    X = np.asarray(member_vecs, dtype=np.float32, order="C")
    Xn = normalize(X, norm="l2", axis=1, copy=True)
    sim = Xn @ Xn.T
    sim = np.clip(sim, -1.0, 1.0)

    w = np.ones(n, dtype=np.int64) if weights is None else np.asarray(weights, dtype=np.int64).ravel()
    if w.shape[0] != n:
        raise ValueError("weights length must match n")
    w = np.maximum(w, 1)

    groups: Dict[int, Set[int]] = {i: {i} for i in range(n)}
    gw: Dict[int, int] = {i: int(w[i]) for i in range(n)}

    inter: Dict[Tuple[int, int], float] = {}
    heap: List[Tuple[float, int, int]] = []

    for i in range(n):
        for j in range(i + 1, n):
            s = float(sim[i, j])
            inter[_pair_key(i, j)] = s
            if s >= min_pair_sim:
                heapq.heappush(heap, (-s, i, j))

    while heap:
        neg_s, ci, cj = heapq.heappop(heap)
        s = -neg_s
        if ci not in groups or cj not in groups or ci == cj:
            continue
        keeper, victim = (ci, cj) if ci < cj else (cj, ci)
        pk = _pair_key(keeper, victim)
        cur = inter.get(pk)
        if cur is None or abs(float(cur) - float(s)) > 1e-3:
            continue
        if gw[keeper] + gw[victim] > int(max_size):
            continue
        if s < float(min_pair_sim) - 1e-9:
            continue

        others = [ck for ck in groups if ck not in (keeper, victim)]
        new_inter: Dict[Tuple[int, int], float] = {}
        for ck in others:
            sk = inter.get(_pair_key(keeper, ck))
            sv = inter.get(_pair_key(victim, ck))
            if sk is None or sv is None:
                new_s = min(
                    _min_inter_from_matrix(groups[keeper], groups[ck], sim),
                    _min_inter_from_matrix(groups[victim], groups[ck], sim),
                )
            else:
                new_s = float(min(sk, sv))
            new_inter[_pair_key(keeper, ck)] = new_s

        groups[keeper] |= groups[victim]
        del groups[victim]
        gw[keeper] = int(gw[keeper] + gw[victim])
        del gw[victim]

        for k in list(inter.keys()):
            if victim in k:
                inter.pop(k, None)

        for pk2, new_s in new_inter.items():
            inter[pk2] = new_s
            if new_s >= float(min_pair_sim):
                a, b = pk2
                heapq.heappush(heap, (-new_s, a, b))

    roots = sorted(groups.keys())
    lab_of_root = {r: i for i, r in enumerate(roots)}
    labels = np.zeros(n, dtype=np.int32)
    for r in roots:
        lab = lab_of_root[r]
        for idx in groups[r]:
            labels[idx] = lab
    return labels, len(roots)


def _point_centroids(vectors: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """每个整数标签一行质心（含空标签行则填 0）。"""
    n, d = vectors.shape
    k = int(labels.max()) + 1 if labels.size else 0
    if k <= 0:
        return np.zeros((0, d), dtype=np.float32)
    sums = np.zeros((k, d), dtype=np.float64)
    cnt = np.zeros(k, dtype=np.int64)
    for i in range(n):
        li = int(labels[i])
        if li >= 0:
            sums[li] += vectors[i].astype(np.float64, copy=False)
            cnt[li] += 1
    out = np.zeros((k, d), dtype=np.float32)
    nz = cnt > 0
    out[nz] = (sums[nz] / cnt[nz, None]).astype(np.float32)
    return out


class AgglomerativeConstrainedClustering(ClusteringAlgorithm):
    """
    受约束凝聚聚类 + 大规模两阶段近似。

    YAML 示例::

        clustering:
          algorithm: agglomerative
          agglomerative:
            max_size: 50
            min_pair_sim: 0.45
            max_n_exact: 4096
            micro_k: 3000
            micro_batch_size: 8192
            micro_max_iter: 100
    """

    def __init__(self, agg_cfg: Dict, random_seed: int = 42):
        self.cfg = dict(agg_cfg or {})
        self.random_seed = int(random_seed)
        self._labels: Optional[np.ndarray] = None
        self._centers: Optional[np.ndarray] = None
        self._n_clusters: int = 0

    def fit(self, vectors: np.ndarray) -> np.ndarray:
        X = np.asarray(vectors, dtype=np.float32, order="C")
        n = X.shape[0]
        max_exact = int(self.cfg.get("max_n_exact", 4096))

        if n <= max_exact:
            labels, g = build_sub_groups(
                X,
                max_size=int(self.cfg.get("max_size", 50)),
                min_pair_sim=float(self.cfg.get("min_pair_sim", 0.45)),
                weights=None,
            )
            self._labels = labels
            self._n_clusters = int(g)
        else:
            micro_k = int(self.cfg.get("micro_k", min(3000, max(500, n // 15))))
            micro_k = max(2, min(micro_k, n))
            batch_size = int(self.cfg.get("micro_batch_size", min(8192, max(256, n // 4))))
            max_it = int(self.cfg.get("micro_max_iter", 100))
            mb = MiniBatchKMeans(
                n_clusters=micro_k,
                random_state=self.random_seed,
                batch_size=batch_size,
                n_init=3,
                max_iter=max_it,
            )
            micro = mb.fit_predict(X).astype(np.int32, copy=False)
            counts = np.bincount(micro, minlength=micro_k).astype(np.int64)
            centers = mb.cluster_centers_.astype(np.float32, copy=False)
            mask = counts > 0
            if not np.all(mask):
                idx = np.nonzero(mask)[0]
                old_to_new = np.full(micro_k, -1, dtype=np.int32)
                old_to_new[idx] = np.arange(idx.size, dtype=np.int32)
                centers = centers[mask]
                counts = counts[mask]
                micro = old_to_new[micro]

            sub_labels, g = build_sub_groups(
                centers,
                max_size=int(self.cfg.get("max_size", 50)),
                min_pair_sim=float(self.cfg.get("min_pair_sim", 0.45)),
                weights=counts,
            )
            point_labels = sub_labels[micro].astype(np.int32, copy=False)
            self._labels = point_labels
            self._n_clusters = int(len(np.unique(point_labels)))

        self._centers = _point_centroids(X, self._labels)
        return self._labels

    def get_cluster_centers(self) -> Optional[np.ndarray]:
        return self._centers

    @property
    def n_clusters(self) -> int:
        return int(self._n_clusters)


def agglomerative_config_from_clustering(clustering: Dict) -> Dict:
    """clustering 字典里 agglomerative 小节，缺省补默认。"""
    return dict(clustering.get("agglomerative") or {})
