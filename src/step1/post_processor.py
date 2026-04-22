"""
Step1 后处理 - 从聚类结果中选择top簇和代表性样本
"""

import json
import random
from pathlib import Path
from typing import List, Dict, Tuple
from collections import Counter

from ..db import LanceVectorStore


def select_top_clusters(
    vector_store: LanceVectorStore,
    top_percent: float = 0.1,
    max_samples_per_cluster: int = 10,
    exclude_noise: bool = True,
    random_seed: int = 42
) -> Dict[int, List[str]]:
    """
    从聚类结果中选择top簇和样本

    Args:
        vector_store: LanceDB向量存储
        top_percent: 选择前百分之多少的簇（按大小排序）
        max_samples_per_cluster: 每个簇最多选择多少个样本
        exclude_noise: 是否排除噪声点（cluster_id=-1）
        random_seed: 随机种子

    Returns:
        {cluster_id: [step_id1, step_id2, ...]}
    """
    random.seed(random_seed)

    # 读取所有数据
    arrow_table = vector_store.table.to_arrow()
    step_ids = arrow_table.column("step_id").to_pylist()
    cluster_ids = arrow_table.column("cluster_id").to_pylist()

    # 统计簇大小
    cluster_sizes = Counter(cluster_ids)

    # 排除噪声点
    if exclude_noise and -1 in cluster_sizes:
        del cluster_sizes[-1]

    # 按大小排序，选择top簇
    sorted_clusters = sorted(cluster_sizes.items(), key=lambda x: -x[1])
    n_top = max(1, int(len(sorted_clusters) * top_percent))
    top_clusters = [cid for cid, _ in sorted_clusters[:n_top]]

    print(f"\nSelecting top {top_percent*100}% clusters:")
    print(f"  Total clusters: {len(sorted_clusters)}")
    print(f"  Selected: {n_top} clusters")
    print(f"  Top cluster sizes: {[cluster_sizes[cid] for cid in top_clusters[:5]]}")

    # 为每个top簇随机选择样本
    selected = {}
    for cluster_id in top_clusters:
        # 找到该簇的所有step_id
        cluster_step_ids = [
            sid for sid, cid in zip(step_ids, cluster_ids)
            if cid == cluster_id
        ]

        # 随机采样
        if len(cluster_step_ids) > max_samples_per_cluster:
            sampled = random.sample(cluster_step_ids, max_samples_per_cluster)
        else:
            sampled = cluster_step_ids

        selected[cluster_id] = sampled
        print(f"  Cluster {cluster_id}: {len(cluster_step_ids)} steps -> selected {len(sampled)}")

    return selected


def load_reasoning_chains_by_step_ids(
    step_ids: List[str],
    chains_jsonl_path: Path
) -> List[Dict]:
    """
    根据step_id列表从JSONL文件中加载对应的reasoning chain

    Args:
        step_ids: step_id列表（格式：paper_id::conclusion_id::step_id）
        chains_jsonl_path: reasoning_chains.jsonl文件路径

    Returns:
        匹配的reasoning chain列表
    """
    # 解析step_id，提取paper_id和conclusion_id
    target_keys = set()
    for step_id in step_ids:
        parts = step_id.split("::")
        if len(parts) >= 3:
            paper_id, conclusion_id = parts[0], parts[1]
            target_keys.add((paper_id, conclusion_id))

    # 读取JSONL，匹配
    matched_chains = []
    with open(chains_jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            chain = json.loads(line)
            key = (chain['paper_id'], chain['conclusion_id'])
            if key in target_keys:
                matched_chains.append(chain)

    print(f"Loaded {len(matched_chains)} reasoning chains for {len(step_ids)} steps")
    return matched_chains


def concatenate_chains_to_text(chains: List[Dict]) -> str:
    """
    将多个reasoning chain拼接成一个文本

    Args:
        chains: reasoning chain列表（dict格式）

    Returns:
        拼接后的文本
    """
    texts = []
    for chain in chains:
        # 标题
        texts.append(f"# {chain['conclusion_title']}")
        texts.append(f"Conclusion: {chain['conclusion_text']}")
        texts.append("")

        # 推理步骤
        texts.append("## Reasoning Steps:")
        for step in chain['steps']:
            texts.append(f"- {step['text']}")
        texts.append("")
        texts.append("---")
        texts.append("")

    return "\n".join(texts)


def save_selected_samples(
    selected: Dict[int, List[str]],
    chains_jsonl_path: Path,
    output_dir: Path
) -> None:
    """
    保存选中的样本到文件

    Args:
        selected: {cluster_id: [step_id1, ...]}
        chains_jsonl_path: reasoning_chains.jsonl路径
        output_dir: 输出目录
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # 保存选择结果（JSON）
    selection_path = output_dir / "selected_clusters.json"
    with open(selection_path, 'w', encoding='utf-8') as f:
        json.dump({
            "n_clusters": len(selected),
            "total_samples": sum(len(v) for v in selected.values()),
            "clusters": {str(k): v for k, v in selected.items()}
        }, f, indent=2)
    print(f"Saved selection to {selection_path}")

    # 为每个簇保存拼接文本
    for cluster_id, step_ids in selected.items():
        chains = load_reasoning_chains_by_step_ids(step_ids, chains_jsonl_path)
        text = concatenate_chains_to_text(chains)

        text_path = output_dir / f"cluster_{cluster_id}_chains.txt"
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"Saved cluster {cluster_id} text to {text_path}")

    # 保存所有簇的汇总文本（用于Step2）
    all_step_ids = [sid for sids in selected.values() for sid in sids]
    all_chains = load_reasoning_chains_by_step_ids(all_step_ids, chains_jsonl_path)
    all_text = concatenate_chains_to_text(all_chains)

    all_text_path = output_dir / "all_selected_chains.txt"
    with open(all_text_path, 'w', encoding='utf-8') as f:
        f.write(all_text)
    print(f"Saved all selected chains to {all_text_path}")


def run_post_processing(
    vector_store: LanceVectorStore,
    chains_jsonl_path: Path,
    output_dir: Path,
    top_percent: float = 0.1,
    max_samples_per_cluster: int = 10
) -> Dict[int, List[str]]:
    """
    执行Step1后处理

    Returns:
        选中的样本字典
    """
    print("\n" + "=" * 60)
    print("Step1 Post-Processing: Select Top Clusters")
    print("=" * 60)

    # 选择top簇
    selected = select_top_clusters(
        vector_store=vector_store,
        top_percent=top_percent,
        max_samples_per_cluster=max_samples_per_cluster
    )

    # 保存结果
    save_selected_samples(
        selected=selected,
        chains_jsonl_path=chains_jsonl_path,
        output_dir=output_dir
    )

    print("\n" + "=" * 60)
    print("Post-Processing Complete!")
    print(f"  Selected {len(selected)} clusters")
    print(f"  Total samples: {sum(len(v) for v in selected.values())}")
    print("=" * 60)

    return selected
