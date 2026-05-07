"""
批量判断所有 clusters 的 workflow 适用性
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.step3.workflow_judge import judge_cluster_async


async def batch_judge_all_clusters(
    selected_chains_path: Path,
    output_path: Path,
    concurrency: int = 5,
    verbose: bool = True,
):
    """
    批量判断所有 clusters

    Args:
        selected_chains_path: selected_chains.json 路径
        output_path: 输出判断结果的路径
        concurrency: 并发数
        verbose: 是否打印详细信息
    """
    # 加载 chains
    with open(selected_chains_path) as f:
        all_chains = json.load(f)

    # 按 cluster 组织
    clusters = {}
    for chain in all_chains:
        cid = chain.get("cluster_id")
        if cid not in clusters:
            clusters[cid] = []
        clusters[cid].append(chain)

    cluster_ids = sorted(clusters.keys())

    print("=" * 70)
    print("Batch Workflow Judgment")
    print("=" * 70)
    print(f"Total clusters: {len(cluster_ids)}")
    print(f"Concurrency: {concurrency}")
    print("=" * 70)

    # 并发判断
    semaphore = asyncio.Semaphore(concurrency)

    async def judge_with_semaphore(cid):
        async with semaphore:
            return await judge_cluster_async(
                cid, clusters[cid], temperature=0.1, verbose=verbose
            )

    tasks = [judge_with_semaphore(cid) for cid in cluster_ids]
    results = await asyncio.gather(*tasks)

    # 整理结果
    judgments = []
    accept_count = 0
    reject_count = 0
    error_count = 0

    for cid, result in zip(cluster_ids, results):
        if result is None:
            error_count += 1
            judgments.append({
                "cluster_id": cid,
                "decision": "ERROR",
                "num_chains": len(clusters[cid]),
            })
        else:
            decision = result.get("decision", "UNKNOWN")
            if decision == "ACCEPT":
                accept_count += 1
            elif decision == "REJECT":
                reject_count += 1

            judgments.append({
                "cluster_id": cid,
                "num_chains": len(clusters[cid]),
                **result,
            })

    # 保存结果
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(judgments, f, ensure_ascii=False, indent=2)

    # 汇总统计
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"Total clusters: {len(cluster_ids)}")
    print(f"  ACCEPT: {accept_count} ({100*accept_count/len(cluster_ids):.1f}%)")
    print(f"  REJECT: {reject_count} ({100*reject_count/len(cluster_ids):.1f}%)")
    print(f"  ERROR: {error_count}")
    print(f"\n✓ Results saved to: {output_path}")

    # 显示 ACCEPT 的 clusters
    print("\n" + "=" * 70)
    print("ACCEPTED Clusters (suitable for workflow extraction):")
    print("=" * 70)
    for j in judgments:
        if j.get("decision") == "ACCEPT":
            print(f"  Cluster {j['cluster_id']}: {j.get('reasoning', '')[:100]}...")

    return judgments


if __name__ == "__main__":
    selected_chains_path = Path("data/step1_output/selected_chains.json")
    output_path = Path("data/workflow_judgments.json")

    asyncio.run(batch_judge_all_clusters(
        selected_chains_path,
        output_path,
        concurrency=5,  # 控制并发，避免 API 限流
        verbose=True,
    ))
