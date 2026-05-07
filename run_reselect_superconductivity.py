#!/usr/bin/env python3
"""
重新选择 Superconductivity 聚类 — 每簇 50 条链，然后下载文件
"""
import json
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.step1.cluster.selector import select_top_clusters, save_selection
from src.db import LanceVectorStore

OUTPUT_DIR = Path("data/Superconductivity/step1_output_agglomerative_v2")
LANCE_DB_DIR = Path("data/Superconductivity/lance_db")

TOP_PERCENT = 0.01     # top 1% of clusters
MAX_PER_CLUSTER = 50   # 50 chains per cluster

def main():
    print("=== 重新选择: 每簇 50 条链 ===\n")

    # 1. 加载聚类标签
    print("[1/4] 加载聚类标签...")
    with open(OUTPUT_DIR / "cluster_labels.json") as f:
        label_dict = json.load(f)

    chain_ids = list(label_dict.keys())
    labels = np.array([label_dict[cid] for cid in chain_ids])
    print(f"  Total chains: {len(chain_ids)}")
    print(f"  Unique clusters: {len(set(labels))}")

    # 2. 加载聚类中心
    print("\n[2/4] 加载聚类中心...")
    centers = np.load(OUTPUT_DIR / "cluster_centers.npy")
    print(f"  Centers shape: {centers.shape}")

    # 3. 初始化 LanceVectorStore
    print("\n[3/4] 初始化 LanceVectorStore...")
    vector_store = LanceVectorStore(
        db_path=LANCE_DB_DIR,
        table_name="chain_embeddings",
    )

    # 4. 重新选择
    print(f"\n[4/4] 选择 top {TOP_PERCENT*100:.0f}% 聚类，每簇最多 {MAX_PER_CLUSTER} 条...")
    result = select_top_clusters(
        vector_store=vector_store,
        centers=centers,
        labels=labels,
        chain_ids=chain_ids,
        top_percent=TOP_PERCENT,
        max_per_cluster=MAX_PER_CLUSTER,
        verbose=True,
        scan_page_size=32768,
    )

    # 5. 保存
    print("\n保存选择结果...")
    save_selection(result, OUTPUT_DIR)

    # 6. 打印统计
    print("\n" + "=" * 60)
    print("选择统计:")
    print(f"  总聚类数: {result['summary']['n_clusters_total']}")
    print(f"  选中聚类数: {result['summary']['n_clusters_selected']}")
    print(f"  选中链数: {result['summary']['n_chains_selected']}")
    unique_papers = len(set(c["paper_id"] for c in result["selected_chains"] if c.get("paper_id")))
    print(f"  唯一论文数: {unique_papers}")
    print("\n每个聚类:")
    for stat in sorted(result["cluster_stats"], key=lambda x: -x["size"]):
        print(f"  Cluster {stat['cluster_id']}: size={stat['size']}, selected={stat['selected_count']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
