"""
Step1 Workflow 文件组织器 - 按 cluster 下载并组织文件到新的目录结构
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Set
from concurrent.futures import ThreadPoolExecutor, as_completed

import tos


def _tos_bucket(config: dict) -> str:
    """桶名：环境变量 TOS_BUCKET 优先，否则使用 YAML 中的 bucket。"""
    b = os.getenv("TOS_BUCKET", "").strip()
    if b:
        return b
    return (config.get("bucket") or "").strip()


def _normalize_tos_endpoint(endpoint: str) -> str:
    """将 S3 格式的 endpoint 转换为 TOS SDK 格式"""
    e = (endpoint or "").strip()
    if e.startswith("tos-s3-"):
        return "tos-" + e[len("tos-s3-"):]
    return e


def _get_tos_client(config: dict) -> tos.TosClientV2:
    endpoint = _normalize_tos_endpoint(
        os.getenv("TOS_ENDPOINT", config.get("endpoint", "tos-cn-beijing.volces.com"))
    )
    return tos.TosClientV2(
        os.getenv("TOS_ACCESS_KEY", config.get("access_key", "")),
        os.getenv("TOS_SECRET_KEY", config.get("secret_key", "")),
        endpoint,
        os.getenv("TOS_REGION", config.get("region", "cn-beijing")),
    )


def normalize_paper_id(paper_id: str) -> str:
    """将 paper_id 中的特殊字符转为文件系统安全格式"""
    return paper_id.replace("/", "%2F")


def organize_selected_chains_by_cluster(
    selected_chains_path: Path
) -> Dict[int, List[Dict]]:
    """
    按 cluster_id 组织 selected_chains.json

    Returns:
        {cluster_id: [chain_dict1, chain_dict2, ...]}
    """
    with open(selected_chains_path, encoding="utf-8") as f:
        data = json.load(f)

    clusters: Dict[int, List[Dict]] = {}
    for item in data:
        cluster_id = item.get("cluster_id")
        if cluster_id is None:
            continue
        if cluster_id not in clusters:
            clusters[cluster_id] = []
        clusters[cluster_id].append(item)

    return clusters


def download_file_from_tos(
    client: tos.TosClientV2,
    bucket: str,
    key: str,
    local_path: Path
) -> bool:
    """从 TOS 下载单个文件"""
    try:
        obj = client.get_object(bucket, key)
        content = obj.read()

        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(content)
        return True
    except Exception as e:
        print(f"  ✗ Failed to download {key}: {e}", flush=True)
        return False


def download_cluster_files(
    cluster_id: int,
    chains: List[Dict],
    output_base_dir: Path,
    tos_config: dict,
    client: tos.TosClientV2,
    bucket: str,
    max_workers: int = 10,
    verbose: bool = True,
) -> Dict[str, int]:
    """
    下载单个 cluster 的所有文件

    新目录结构:
    data/workflows/cluster_{id}/
        ├── md/
        │   ├── paper1.md
        │   └── paper2.md
        ├── xml/
        │   ├── chain1.xml
        │   └── chain2.xml
        └── selected_chains.json

    Returns:
        {"xml_success": n, "md_success": n, "total_chains": n, "total_papers": n}
    """
    cluster_dir = output_base_dir / f"cluster_{cluster_id}"
    md_dir = cluster_dir / "md"
    xml_dir = cluster_dir / "xml"

    md_dir.mkdir(parents=True, exist_ok=True)
    xml_dir.mkdir(parents=True, exist_ok=True)

    # 保存 selected_chains.json
    with open(cluster_dir / "selected_chains.json", "w", encoding="utf-8") as f:
        json.dump(chains, f, ensure_ascii=False, indent=2)

    # 提取所有 paper_id 和 chain_id
    paper_ids: Set[str] = set()
    chain_ids: List[tuple[str, str]] = []  # (chain_id, paper_id)

    for chain in chains:
        paper_id = chain.get("paper_id")
        chain_id = chain.get("chain_id")
        if paper_id:
            paper_ids.add(paper_id)
        if chain_id and paper_id:
            chain_ids.append((chain_id, paper_id))

    stats = {
        "xml_success": 0,
        "md_success": 0,
        "total_chains": len(chain_ids),
        "total_papers": len(paper_ids),
    }

    if verbose:
        print(f"\n[Cluster {cluster_id}] Downloading {len(chain_ids)} chains, {len(paper_ids)} papers...", flush=True)

    # 下载 XML 文件（思维链）
    def download_xml(chain_id: str, paper_id: str) -> bool:
        fs_id = normalize_paper_id(paper_id)
        xml_key = f"{tos_config['xml_source_prefix']}{fs_id}_reasoning_chain.xml"
        xml_path = xml_dir / f"{chain_id}.xml"
        return download_file_from_tos(client, bucket, xml_key, xml_path)

    # 下载 MD 文件（论文）
    def download_md(paper_id: str) -> bool:
        fs_id = normalize_paper_id(paper_id)
        md_key_candidates = [
            f"{tos_config['md_prefix']}{fs_id}.md",
            f"{tos_config['md_prefix']} /{fs_id}.md",  # TOS has space before slash
            f"{tos_config['md_prefix']}{paper_id}.md",
            f"{tos_config['md_prefix']} /{paper_id}.md",
        ]

        md_path = md_dir / f"{fs_id}.md"
        for md_key in md_key_candidates:
            if download_file_from_tos(client, bucket, md_key, md_path):
                return True
        return False

    # 并发下载 XML
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        xml_futures = {
            executor.submit(download_xml, chain_id, paper_id): chain_id
            for chain_id, paper_id in chain_ids
        }

        for future in as_completed(xml_futures):
            if future.result():
                stats["xml_success"] += 1

    # 并发下载 MD
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        md_futures = {
            executor.submit(download_md, paper_id): paper_id
            for paper_id in paper_ids
        }

        for future in as_completed(md_futures):
            if future.result():
                stats["md_success"] += 1

    if verbose:
        print(
            f"  ✓ Cluster {cluster_id}: "
            f"XML {stats['xml_success']}/{stats['total_chains']}, "
            f"MD {stats['md_success']}/{stats['total_papers']}",
            flush=True
        )

    return stats


def run_workflow_file_organizer(
    selected_chains_path: Path,
    output_base_dir: Path,
    tos_config: dict,
    max_workers: int = 10,
    verbose: bool = True,
) -> Dict[int, Dict[str, int]]:
    """
    执行 workflow 文件组织流程

    Args:
        selected_chains_path: selected_chains.json 路径
        output_base_dir: 输出根目录（例如 data/workflows）
        tos_config: TOS 配置
        max_workers: 并发数
        verbose: 详细日志

    Returns:
        {cluster_id: stats}
    """
    print("\n" + "=" * 60)
    print("Step1 Workflow File Organizer: Organizing files by cluster")
    print("=" * 60)

    # 1. 按 cluster 组织 selected_chains
    print("\n[1/2] Organizing selected chains by cluster...", flush=True)
    clusters = organize_selected_chains_by_cluster(selected_chains_path)

    total_chains = sum(len(chains) for chains in clusters.values())
    print(f"  ✓ Found {len(clusters)} clusters, {total_chains} chains", flush=True)

    # 2. 下载文件
    print(f"\n[2/2] Downloading files (max_workers={max_workers})...", flush=True)

    client = _get_tos_client(tos_config)
    bucket = _tos_bucket(tos_config)

    all_stats: Dict[int, Dict[str, int]] = {}

    for cluster_id, chains in sorted(clusters.items()):
        stats = download_cluster_files(
            cluster_id, chains, output_base_dir,
            tos_config, client, bucket, max_workers, verbose
        )
        all_stats[cluster_id] = stats

    # 3. 汇总统计
    total_xml = sum(s["xml_success"] for s in all_stats.values())
    total_md = sum(s["md_success"] for s in all_stats.values())
    total_chains_expected = sum(s["total_chains"] for s in all_stats.values())
    total_papers_expected = sum(s["total_papers"] for s in all_stats.values())

    print("\n" + "=" * 60)
    print("Workflow File Organization Complete!")
    print(f"  Clusters: {len(all_stats)}")
    print(f"  XML files: {total_xml}/{total_chains_expected}")
    print(f"  MD files: {total_md}/{total_papers_expected}")
    print(f"  Output: {output_base_dir}")
    print("=" * 60)

    return all_stats
