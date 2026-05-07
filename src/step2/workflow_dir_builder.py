"""
Workflow 目录构建模块 - 为每个聚类构建 Workflower 输入目录
"""

import json
from pathlib import Path
from typing import Dict, List, Set
from concurrent.futures import ThreadPoolExecutor, as_completed

import tos

from ..step1.file_downloader import (
    _get_tos_client,
    _tos_bucket,
    download_file_from_tos,
    normalize_paper_id,
)


def build_workflow_directory(
    cluster_meta: Dict,
    chains: List[Dict],
    output_dir: Path,
    tos_config: Dict,
    max_workers: int = 10,
    verbose: bool = True
) -> Path:
    """
    为单个聚类构建 Workflower 输入目录

    Args:
        cluster_meta: 聚类元数据（来自 cluster_metadata 表）
        chains: 该聚类的所有思维链（来自 chain_embeddings 表）
        output_dir: 输出根目录
        tos_config: TOS 配置
        max_workers: 并发下载线程数
        verbose: 是否打印详细日志

    Returns:
        创建的目录路径
    """
    domain = cluster_meta["domain"]
    local_cluster_id = cluster_meta["local_cluster_id"]
    cluster_dir = output_dir / f"cluster_{local_cluster_id}"

    if verbose:
        print(f"\n[Cluster {local_cluster_id}] Building workflow directory...", flush=True)
        print(f"  Domain: {domain}", flush=True)
        print(f"  Chains: {len(chains)}", flush=True)
        print(f"  Papers: {cluster_meta['num_papers']}", flush=True)

    # 1. 创建目录结构
    cluster_dir.mkdir(parents=True, exist_ok=True)
    (cluster_dir / "md").mkdir(exist_ok=True)
    (cluster_dir / "xml").mkdir(exist_ok=True)

    # 2. 写入 selected_chains.json
    selected_chains = []
    for chain in chains:
        selected_chains.append({
            "chain_id": chain["chain_id"],
            "paper_id": chain["paper_id"],
            "cluster_id": chain["cluster_id"],
            "journal": chain["journal"],
            "conclusion_id": chain["conclusion_id"],
            "conclusion_title": chain["conclusion_title"],
            "chain_text": chain["chain_text"],
            "num_steps": chain["num_steps"],
            "has_citations": chain["has_citations"],
            "has_figures": chain["has_figures"],
        })

    selected_chains_path = cluster_dir / "selected_chains.json"
    with open(selected_chains_path, "w", encoding="utf-8") as f:
        json.dump(selected_chains, f, indent=2, ensure_ascii=False)

    if verbose:
        print(f"  ✓ Wrote selected_chains.json ({len(selected_chains)} chains)", flush=True)

    # 3. 下载文件
    if verbose:
        print(f"  Downloading files from TOS...", flush=True)

    # 提取唯一的 paper_ids
    paper_ids = list(set(chain["paper_id"] for chain in chains))

    # 初始化 TOS 客户端
    client = _get_tos_client(tos_config)
    bucket = _tos_bucket(tos_config)

    # 并发下载
    stats = {"xml_success": 0, "md_success": 0, "xml_failed": [], "md_failed": []}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有下载任务
        futures = {}

        # 下载 XML 文件（每条链一个文件）
        for chain in chains:
            paper_id = chain["paper_id"]
            conclusion_id = chain["conclusion_id"]
            fs_id = normalize_paper_id(paper_id)

            # XML 路径：{tos_prefix}/xml/{paper_id}_{conclusion_id}.xml
            xml_key = f"{tos_config.get('xml_prefix', 'paper_ocr/xml/')}{fs_id}_{conclusion_id}.xml"
            xml_local_path = cluster_dir / "xml" / f"{fs_id}_{conclusion_id}.xml"

            future = executor.submit(
                download_file_from_tos,
                client, bucket, xml_key, xml_local_path
            )
            futures[future] = ("xml", paper_id, conclusion_id)

        # 下载 MD 文件（每篇论文一个文件，去重）
        for paper_id in paper_ids:
            fs_id = normalize_paper_id(paper_id)

            # MD 路径：{tos_prefix}/md/{paper_id}.md
            md_key = f"{tos_config.get('md_prefix', 'paper_ocr/md/')}{fs_id}.md"
            md_local_path = cluster_dir / "md" / f"{fs_id}.md"

            future = executor.submit(
                download_file_from_tos,
                client, bucket, md_key, md_local_path
            )
            futures[future] = ("md", paper_id, None)

        # 收集结果
        for future in as_completed(futures):
            file_type, paper_id, conclusion_id = futures[future]
            try:
                success = future.result()
                if success:
                    if file_type == "xml":
                        stats["xml_success"] += 1
                    else:
                        stats["md_success"] += 1
                else:
                    if file_type == "xml":
                        stats["xml_failed"].append(f"{paper_id}_{conclusion_id}")
                    else:
                        stats["md_failed"].append(paper_id)
            except Exception as e:
                if file_type == "xml":
                    stats["xml_failed"].append(f"{paper_id}_{conclusion_id}")
                else:
                    stats["md_failed"].append(paper_id)
                if verbose:
                    print(f"  ✗ Download error: {e}", flush=True)

    # 4. 报告统计
    if verbose:
        print(f"  ✓ Downloaded {stats['xml_success']}/{len(chains)} XML files", flush=True)
        print(f"  ✓ Downloaded {stats['md_success']}/{len(paper_ids)} MD files", flush=True)

        if stats["xml_failed"]:
            print(f"  ⚠ Failed XML: {len(stats['xml_failed'])} files", flush=True)
        if stats["md_failed"]:
            print(f"  ⚠ Failed MD: {len(stats['md_failed'])} files", flush=True)

    # 5. 写入统计信息
    stats_path = cluster_dir / "download_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    if verbose:
        print(f"  ✓ Workflow directory ready: {cluster_dir}", flush=True)

    return cluster_dir
