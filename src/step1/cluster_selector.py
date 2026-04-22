"""
聚类选择模块 - 选 top 10% 的簇，每簇取离中心最近的 10 个点
"""

import json
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple
from collections import Counter, defaultdict

from ..db import LanceVectorStore


def select_top_clusters(
    vector_store: LanceVectorStore,
    centers: np.ndarray,
    labels: np.ndarray,
    chain_ids: List[str],
    top_percent: float = 0.1,
    max_per_cluster: int = 10,
    verbose: bool = True
) -> Dict:
    """
    选 top N% 簇（按大小），每簇取离中心最近的 K 个点。

    Returns:
        {
            "selected_chains": [{chain_id, cluster_id, distance, paper_id, chain_text}, ...],
            "cluster_stats": [{cluster_id, size, selected_count}, ...],
            "summary": {n_clusters_total, n_clusters_selected, n_chains_selected}
        }
    """
    # 1. 读向量和元数据
    arrow_table = vector_store.table.to_arrow()
    vectors = np.array(arrow_table.column("vector").to_pylist(), dtype=np.float32)
    meta_paper_ids = arrow_table.column("paper_id").to_pylist()
    meta_chain_texts = arrow_table.column("chain_text").to_pylist()

    # chain_id → index 映射
    id_to_idx = {cid: i for i, cid in enumerate(chain_ids)}

    # 2. 按簇分组
    cluster_members = defaultdict(list)  # cluster_id -> [idx_in_chain_ids]
    for i, label in enumerate(labels):
        if label >= 0:
            cluster_members[int(label)].append(i)

    # 3. 按簇大小排序，选 top N%
    sorted_clusters = sorted(cluster_members.items(), key=lambda x: -len(x[1]))
    n_top = max(1, int(len(sorted_clusters) * top_percent))
    top_clusters = sorted_clusters[:n_top]

    if verbose:
        total_clusters = len(sorted_clusters)
        print(f"\n=== Cluster Selection ===")
        print(f"Total clusters: {total_clusters}")
        print(f"Top {top_percent*100:.0f}%: {n_top} clusters")
        sizes = [len(members) for _, members in top_clusters]
        print(f"Size range: {min(sizes)} ~ {max(sizes)}")

    # 4. 每簇取离中心最近的 K 个点
    selected_chains = []
    cluster_stats = []

    for cluster_id, member_indices in top_clusters:
        center = centers[cluster_id]
        # 计算每个成员到中心的距离
        member_vectors = vectors[member_indices]
        distances = np.linalg.norm(member_vectors - center, axis=1)
        # 取最近的 K 个
        k = min(max_per_cluster, len(member_indices))
        nearest_idx = np.argsort(distances)[:k]

        for j in nearest_idx:
            global_idx = member_indices[j]
            selected_chains.append({
                "chain_id": chain_ids[global_idx],
                "cluster_id": cluster_id,
                "distance": float(distances[j]),
                "paper_id": meta_paper_ids[global_idx],
                "chain_text": meta_chain_texts[global_idx],
            })

        cluster_stats.append({
            "cluster_id": cluster_id,
            "size": len(member_indices),
            "selected_count": k,
        })

    if verbose:
        print(f"Selected {len(selected_chains)} chains from {n_top} clusters")
        unique_papers = len(set(c["paper_id"] for c in selected_chains))
        print(f"Unique papers: {unique_papers}")

    return {
        "selected_chains": selected_chains,
        "cluster_stats": cluster_stats,
        "summary": {
            "n_clusters_total": len(sorted_clusters),
            "n_clusters_selected": n_top,
            "n_chains_selected": len(selected_chains),
        }
    }


def save_selection(result: Dict, output_dir: Path) -> None:
    """保存选择结果"""
    output_dir.mkdir(parents=True, exist_ok=True)

    # 完整结果
    with open(output_dir / "selected_chains.json", 'w', encoding='utf-8') as f:
        json.dump(result["selected_chains"], f, ensure_ascii=False, indent=2)

    # 统计
    with open(output_dir / "selection_stats.json", 'w') as f:
        json.dump({
            "summary": result["summary"],
            "cluster_stats": result["cluster_stats"],
        }, f, indent=2)

    # paper_id 列表（去重）
    paper_ids = sorted(set(c["paper_id"] for c in result["selected_chains"]))
    with open(output_dir / "selected_paper_ids.json", 'w') as f:
        json.dump({"count": len(paper_ids), "paper_ids": paper_ids}, f, indent=2)

    print(f"Saved selection to {output_dir}: {len(result['selected_chains'])} chains, {len(paper_ids)} papers")
