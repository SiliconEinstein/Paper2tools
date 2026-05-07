"""
按簇对 selected_chains.json 做「每簇最多 K 条」子采样，用于 workflow 对比实验。

- 若某簇条数 <= K：保留全部（按 distance 排序，与 Step3 簇内顺序一致）。
- 若某簇条数 > K：随机无放回抽取 K 条（可复现 seed）。
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any, Dict, List


def subsample_selected_chains(
    rows: List[Dict[str, Any]],
    chains_per_cluster: int,
    seed: int,
) -> List[Dict[str, Any]]:
    """
    Args:
        rows: selected_chains.json 解析后的列表
        chains_per_cluster: 每簇保留的链数上限 K
        seed: 随机种子（仅当某簇需要下采样时生效）

    Returns:
        新的行列表（各簇块按 cluster_id 升序拼接）
    """
    if chains_per_cluster < 1:
        raise ValueError("chains_per_cluster must be >= 1")

    by_cluster: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict) or "cluster_id" not in row:
            continue
        try:
            cid = int(row["cluster_id"])
        except (TypeError, ValueError):
            continue
        by_cluster[cid].append(row)

    rng = random.Random(seed)
    out: List[Dict[str, Any]] = []
    for cid in sorted(by_cluster.keys()):
        members = by_cluster[cid]
        members.sort(key=lambda m: (m.get("distance") is None, m.get("distance") or 0.0))
        if len(members) <= chains_per_cluster:
            chosen = members
        else:
            chosen = rng.sample(members, chains_per_cluster)
        out.extend(chosen)
    return out
