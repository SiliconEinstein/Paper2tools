"""
Step1 文件下载器 - 为每个 cluster 下载相关的 XML 和 MD 文件
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


def extract_paper_ids_from_selected_chains(
    selected_chains_path: Path
) -> Dict[int, Set[str]]:
    """
    从 selected_chains.json 中提取每个 cluster 对应的 paper_id 集合

    Args:
        selected_chains_path: selected_chains.json 文件路径

    Returns:
        {cluster_id: {paper_id1, paper_id2, ...}}
    """
    with open(selected_chains_path, encoding="utf-8") as f:
        data = json.load(f)

    cluster_papers: Dict[int, Set[str]] = {}

    for item in data:
        cluster_id = item.get("cluster_id")
        paper_id = item.get("paper_id")

        if cluster_id is None or paper_id is None:
            continue

        if cluster_id not in cluster_papers:
            cluster_papers[cluster_id] = set()
        cluster_papers[cluster_id].add(paper_id)

    return cluster_papers


def download_file_from_tos(
    client: tos.TosClientV2,
    bucket: str,
    key: str,
    local_path: Path
) -> bool:
    """
    从 TOS 下载单个文件

    Returns:
        True if successful, False otherwise
    """
    try:
        obj = client.get_object(bucket, key)
        content = obj.read()

        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(content)
        return True
    except Exception as e:
        print(f"  ✗ Failed to download {key}: {e}", flush=True)
        return False


def download_paper_files(
    paper_id: str,
    cluster_id: int,
    output_base_dir: Path,
    tos_config: dict,
    client: tos.TosClientV2,
    bucket: str,
) -> tuple[bool, bool]:
    """
    下载单篇论文的 XML 和 MD 文件到对应 cluster 文件夹

    Returns:
        (xml_success, md_success)
    """
    fs_id = normalize_paper_id(paper_id)
    cluster_dir = output_base_dir / f"cluster_{cluster_id}"
    cluster_dir.mkdir(parents=True, exist_ok=True)

    # 下载 XML
    xml_key = f"{tos_config['xml_source_prefix']}{fs_id}_reasoning_chain.xml"
    xml_path = cluster_dir / f"{fs_id}_reasoning_chain.xml"
    xml_success = download_file_from_tos(client, bucket, xml_key, xml_path)

    # 下载 MD（尝试多个可能的路径）
    md_key_candidates = [
        f"{tos_config['md_prefix']}{fs_id}.md",
        f"{tos_config['md_prefix']}{paper_id}.md",
    ]

    md_success = False
    for md_key in md_key_candidates:
        md_path = cluster_dir / f"{fs_id}.md"
        if download_file_from_tos(client, bucket, md_key, md_path):
            md_success = True
            break

    return xml_success, md_success


def download_cluster_files(
    cluster_papers: Dict[int, Set[str]],
    output_base_dir: Path,
    tos_config: dict,
    max_workers: int = 10,
    verbose: bool = True,
) -> Dict[int, Dict[str, int]]:
    """
    并发下载所有 cluster 的文件

    Args:
        cluster_papers: {cluster_id: {paper_id1, ...}}
        output_base_dir: 输出根目录（例如 data/step1_output/clusters）
        tos_config: TOS 配置
        max_workers: 并发线程数
        verbose: 是否打印详细日志

    Returns:
        {cluster_id: {"xml_success": n, "md_success": n, "total": n}}
    """
    client = _get_tos_client(tos_config)
    bucket = _tos_bucket(tos_config)

    stats: Dict[int, Dict[str, int]] = {}

    for cluster_id, paper_ids in cluster_papers.items():
        if verbose:
            print(f"\n[Cluster {cluster_id}] Downloading {len(paper_ids)} papers...", flush=True)

        stats[cluster_id] = {"xml_success": 0, "md_success": 0, "total": len(paper_ids)}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    download_paper_files,
                    paper_id, cluster_id, output_base_dir,
                    tos_config, client, bucket
                ): paper_id
                for paper_id in paper_ids
            }

            for future in as_completed(futures):
                paper_id = futures[future]
                try:
                    xml_ok, md_ok = future.result()
                    if xml_ok:
                        stats[cluster_id]["xml_success"] += 1
                    if md_ok:
                        stats[cluster_id]["md_success"] += 1
                except Exception as e:
                    if verbose:
                        print(f"  ✗ Error processing {paper_id}: {e}", flush=True)

        if verbose:
            s = stats[cluster_id]
            print(
                f"  ✓ Cluster {cluster_id}: "
                f"XML {s['xml_success']}/{s['total']}, "
                f"MD {s['md_success']}/{s['total']}",
                flush=True
            )

    return stats


def run_file_download(
    selected_chains_path: Path,
    output_base_dir: Path,
    tos_config: dict,
    max_workers: int = 10,
    verbose: bool = True,
) -> Dict[int, Dict[str, int]]:
    """
    执行文件下载流程

    Args:
        selected_chains_path: selected_chains.json 路径
        output_base_dir: 输出根目录
        tos_config: TOS 配置
        max_workers: 并发数
        verbose: 详细日志

    Returns:
        下载统计
    """
    print("\n" + "=" * 60)
    print("Step1 File Download: Downloading XML and MD files")
    print("=" * 60)

    # 1. 提取 paper_id
    print("\n[1/2] Extracting paper IDs from selected chains...", flush=True)
    cluster_papers = extract_paper_ids_from_selected_chains(selected_chains_path)

    total_papers = sum(len(papers) for papers in cluster_papers.values())
    print(f"  ✓ Found {len(cluster_papers)} clusters, {total_papers} unique papers", flush=True)

    # 2. 下载文件
    print(f"\n[2/2] Downloading files (max_workers={max_workers})...", flush=True)
    stats = download_cluster_files(
        cluster_papers, output_base_dir, tos_config, max_workers, verbose
    )

    # 3. 汇总统计
    total_xml = sum(s["xml_success"] for s in stats.values())
    total_md = sum(s["md_success"] for s in stats.values())
    total_expected = sum(s["total"] for s in stats.values())

    print("\n" + "=" * 60)
    print("File Download Complete!")
    print(f"  Clusters: {len(stats)}")
    print(f"  XML files: {total_xml}/{total_expected}")
    print(f"  MD files: {total_md}/{total_expected}")
    print(f"  Output: {output_base_dir}")
    print("=" * 60)

    return stats
