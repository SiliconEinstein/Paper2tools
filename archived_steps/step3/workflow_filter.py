"""
Workflow 质量过滤器 - 使用 workflow-filter skill 判断 workflow 是否值得提取
"""

import json
import sys
from pathlib import Path
from typing import Dict, List

import yaml


def load_chains_by_cluster(selected_chains_path: Path) -> Dict[int, List[Dict]]:
    """按 cluster_id 组织 chains"""
    with open(selected_chains_path, encoding="utf-8") as f:
        chains = json.load(f)

    clusters = {}
    for chain in chains:
        cid = chain.get("cluster_id")
        if cid is not None:
            if cid not in clusters:
                clusters[cid] = []
            clusters[cid].append(chain)

    return clusters


def format_chains_for_judgment(cluster_id: int, chains: List[Dict]) -> str:
    """格式化 chains 用于 LLM 判断"""
    prompt = f"""# Cluster {cluster_id} - Reasoning Chains

Total chains: {len(chains)}

## Chain Texts:

"""
    for i, chain in enumerate(chains, 1):
        text = chain.get("chain_text", "")
        # 截断过长的文本
        if len(text) > 1000:
            text = text[:1000] + "..."
        prompt += f"### Chain {i} (paper_id: {chain.get('paper_id', 'unknown')})\n\n{text}\n\n"

    prompt += """
---

Based on the above reasoning chains, judge whether this cluster is suitable for extracting a concrete, actionable workflow.

Apply the strict filtering rules defined in the workflow-filter skill.

Output your judgment in JSON format as specified.
"""
    return prompt


def judge_cluster_with_skill(cluster_id: int, chains: List[Dict]) -> Dict:
    """
    使用 workflow-filter skill 判断 cluster

    注意：这个函数需要在 Claude Code 环境中通过 Skill tool 调用
    这里只是生成 prompt，实际调用需要在主流程中完成
    """
    prompt = format_chains_for_judgment(cluster_id, chains)

    # 返回格式化的 prompt，由调用方通过 Skill tool 执行
    return {
        "cluster_id": cluster_id,
        "prompt": prompt,
        "num_chains": len(chains),
    }


def batch_judge_clusters(
    selected_chains_path: Path,
    output_path: Path,
    cluster_ids: List[int] = None,
) -> None:
    """
    批量判断 clusters

    Args:
        selected_chains_path: selected_chains.json 路径
        output_path: 输出判断结果的路径
        cluster_ids: 要判断的 cluster_id 列表，None 表示全部
    """
    clusters = load_chains_by_cluster(selected_chains_path)

    if cluster_ids is None:
        cluster_ids = sorted(clusters.keys())

    print(f"准备判断 {len(cluster_ids)} 个 clusters...")

    # 生成所有 prompts
    judgments = []
    for cid in cluster_ids:
        if cid not in clusters:
            print(f"  ⚠ Cluster {cid} 不存在，跳过")
            continue

        judgment_input = judge_cluster_with_skill(cid, clusters[cid])
        judgments.append(judgment_input)

    # 保存 prompts 供后续处理
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(judgments, f, ensure_ascii=False, indent=2)

    print(f"✓ 已生成 {len(judgments)} 个判断任务，保存到: {output_path}")
    print(f"\n下一步：使用 workflow-filter skill 对每个 cluster 进行判断")


if __name__ == "__main__":
    # 示例用法
    selected_chains_path = Path("data/step1_output/selected_chains.json")
    output_path = Path("data/workflow_filter_tasks.json")

    # 可以指定要判断的 cluster_ids，或者传 None 判断全部
    # cluster_ids = [37, 110, 130, 149, 208, 245]  # 测试用
    cluster_ids = None  # 全部

    batch_judge_clusters(selected_chains_path, output_path, cluster_ids)
