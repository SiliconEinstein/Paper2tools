#!/usr/bin/env python3
"""
通用领域 Step1 流程：向量化 + 聚类 + 选择代表性样本 + 下载 xml/md

用法:
    python run_step1_domain.py --domain materials_science
    python run_step1_domain.py --domain environmental_science
    python run_step1_domain.py --domain superconductivity

流程:
    1. 如果 data/{domain}/step1_output/paper_ids.json 存在，直接读取 paper_ids
    2. 否则从 TOS 按期刊配置构建 paper_ids
    3. 向量化 + 聚类
    4. 选择前 10% 的簇，每簇取离簇中心最近的 50 条链
    5. 下载对应的 xml 和 md 文件到 data/{domain}/workflows/
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import lancedb
import numpy as np
import tos
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parent
os.chdir(REPO)
load_dotenv(REPO / ".env")

from src.step1.pipeline import run_step1_pipeline_async
from src.step1.clustering import select_top_clusters, save_selection, parse_selection_config
from src.db import LanceVectorStore

# ── 常量 ──────────────────────────────────────────────
TOP_PERCENT = 0.10
TOP_N_PER_CLUSTER = 50
MAX_WORKERS = 10
XML_PREFIX = "paper_ocr/xml/"
MD_PREFIX = "paper_ocr/md/"

# ── 领域 → 目录名映射（与 domain_journals.yaml 中的 key 一致）──
DOMAIN_DIR_MAP = {
    "superconductivity": "Superconductivity",
    "materials_science": "materials_science",
    "environmental_science": "environmental_science",
    "mathematics": "mathematics",
    "fluid_mechanics": "fluid_mechanics",
}


def _domain_dir(domain: str) -> str:
    return DOMAIN_DIR_MAP.get(domain, domain)


def _build_config(domain: str) -> dict:
    """动态构建 step1 配置（不需要单独的 yaml 文件）"""
    d = _domain_dir(domain)
    return {
        "data": {
            "journal_config_path": "configs/domain_journals.yaml",
            "target_domain": domain,
            "cache_dir": f"data/{d}/cache",
            "output_dir": f"data/{d}/step1_output",
            "lance_db_dir": "data/lance_db",
            "force_rebuild_ids": False,
            "force_reload_chains": False,
            "batch_size": 500,
            "max_workers": 300,
            "verbose": True,
        },
        "vectorizer": {
            "model": "text-embedding-v4",
            "dimension": 512,
            "concurrency": 10,
            "max_retries": 5,
            "http_timeout": 30,
            "api_batch_size": 10,
        },
        "clustering": {
            "algorithm": "agglomerative",
            "device": "auto",
            "agglomerative": {
                "max_size": 500,
                "min_pair_sim": 0.55,
                "max_n_exact": 4096,
                "micro_k": 3000,
                "micro_batch_size": 8192,
                "micro_max_iter": 100,
            },
            "cosine_metrics": {
                "enabled": True,
                "subsample_n": 5000,
                "max_points_per_cluster": 32,
                "cosine_split_threshold": 0.85,
                "sim_block_rows": 256,
                "random_state": 42,
            },
            "selection": {
                "top_percent": TOP_PERCENT,
                "max_per_cluster": TOP_N_PER_CLUSTER,
            },
        },
        "runtime": {
            "random_seed": 42,
            "verbose": True,
            "skip_vectorization": False,
        },
    }


def _sync_paper_ids(config: dict) -> None:
    """如果 step1_output/paper_ids.json 存在，同步到 cache_dir 供 data_loader 使用"""
    data = config["data"]
    domain = data["target_domain"]
    output_dir = Path(data["output_dir"])
    cache_dir = Path(data["cache_dir"])

    # 支持两种文件名: paper_ids.json 或 paper_ids_{domain}.json
    simple_path = output_dir / "paper_ids.json"
    domain_path = output_dir / f"paper_ids_{domain}.json"
    found_path = None
    if domain_path.is_file():
        found_path = domain_path
    elif simple_path.is_file():
        found_path = simple_path
    if found_path is None:
        return

    # 读取并判断格式
    with open(found_path, encoding="utf-8") as f:
        raw = json.load(f)

    # 支持三种格式:
    # 1. [id1, id2, ...] — 纯列表
    # 2. {"paper_ids": [...], ...} — 完整 cache 格式（含 domain/journals 元数据）
    # 3. 其他 dict — 不识别
    if isinstance(raw, list):
        paper_ids = raw
        cache_data = {
            "domain": domain,
            "journals": [],
            "created_at": "",
            "total_count": len(paper_ids),
            "per_journal_count": {},
            "paper_ids": paper_ids,
        }
    elif isinstance(raw, dict) and "paper_ids" in raw:
        paper_ids = raw["paper_ids"]
        cache_data = raw  # 已经是完整格式，直接使用
    else:
        print(f"WARNING: {found_path} 格式不识别，跳过")
        return

    print(f"[paper_ids] 从 {found_path} 读取 {len(paper_ids)} 个 paper_id")

    # 写到 cache_dir 供 data_loader 使用
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"paper_ids_{domain}.json"

    if not cache_path.exists() or cache_path.stat().st_mtime < found_path.stat().st_mtime:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        print(f"[paper_ids] 已同步到 {cache_path}")


def _print_banner(domain: str, config: dict) -> None:
    algo = config["clustering"]["algorithm"].upper()
    output_dir = config["data"]["output_dir"]
    lance_dir = config["data"]["lance_db_dir"]
    print(f"\n{'='*80}")
    print(f"Step1 通用流程: {domain}")
    print(f"{'='*80}")
    print(f"  聚类算法: {algo}")
    print(f"  输出目录: {output_dir}")
    print(f"  向量库:   {lance_dir}")
    print(f"{'='*80}\n")


# ── TOS 下载 ──────────────────────────────────────────
def _tos_client() -> tos.TosClientV2:
    endpoint = os.getenv("TOS_ENDPOINT", "tos-cn-beijing.volces.com").strip()
    if endpoint.startswith("tos-s3-"):
        endpoint = "tos-" + endpoint[len("tos-s3-"):]
    return tos.TosClientV2(
        os.getenv("TOS_ACCESS_KEY", ""),
        os.getenv("TOS_SECRET_KEY", ""),
        endpoint,
        os.getenv("TOS_REGION", "cn-beijing"),
    )


def _tos_bucket() -> str:
    return os.getenv("TOS_BUCKET", "").strip()


def _download_file(client, bucket, key, local_path: Path) -> bool:
    try:
        obj = client.get_object(bucket, key)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(obj.read())
        return True
    except Exception:
        return False


def download_workflows(
    output_dir: Path,
    lance_db_dir: Path,
    workflows_dir: Path,
    top_percent: float,
    top_n: int,
) -> None:
    """从聚类结果中选出 top 簇、取最近链、下载 xml/md"""
    centers_path = output_dir / "cluster_centers.npy"
    labels_path = output_dir / "cluster_labels.json"
    stats_path = output_dir / "cluster_stats.json"

    if not centers_path.exists():
        print("ERROR: cluster_centers.npy 不存在，跳过下载")
        return

    # 1. 确定目标簇
    with open(stats_path) as f:
        stats = json.load(f)
    sizes = stats["cluster_sizes"]
    sorted_ids = sorted(sizes.keys(), key=lambda k: sizes[k], reverse=True)
    n_top = max(1, int(len(sorted_ids) * top_percent))
    top_ids = [int(cid) for cid in sorted_ids[:n_top]]
    print(f"\n[下载] 目标簇: {len(top_ids)} 个 (top {top_percent*100:.0f}%)")

    # 2. 加载簇中心
    centers = np.load(centers_path)
    print(f"[下载] cluster_centers: {centers.shape}")

    # 3. 按 cluster_id 分组 chain_id
    with open(labels_path) as f:
        labels = json.load(f)
    top_ids_set = set(top_ids)
    cluster_to_chains: dict[int, list[str]] = {cid: [] for cid in top_ids}
    for chain_id, cluster_id in labels.items():
        if cluster_id in top_ids_set:
            cluster_to_chains[cluster_id].append(chain_id)
    total_chains = sum(len(v) for v in cluster_to_chains.values())
    print(f"[下载] 共 {total_chains} 条链分布在 {len(top_ids)} 个簇")

    # 4. 从 LanceDB 查询向量，选最近的 top_n
    print(f"[下载] 从 LanceDB 查询并选择每簇 top {top_n}...", flush=True)
    db = lancedb.connect(str(lance_db_dir))
    table = db.open_table("chain_embeddings")

    cluster_selected: dict[int, list[dict]] = {}
    total_selected = 0
    BATCH = 1000

    for i, cid in enumerate(sorted(top_ids)):
        chain_ids = cluster_to_chains[cid]
        if not chain_ids:
            continue

        rows = []
        for j in range(0, len(chain_ids), BATCH):
            batch_ids = chain_ids[j:j+BATCH]
            id_list = ",".join(f"'{x}'" for x in batch_ids)
            sub = table.search().where(f"chain_id IN ({id_list})").limit(BATCH * 2).to_list()
            rows.extend(sub)

        if not rows:
            continue

        center = centers[cid]
        center_norm = center / (np.linalg.norm(center) + 1e-12)

        scored = []
        for row in rows:
            vec = np.array(row["vector"], dtype=np.float32)
            vec_norm = vec / (np.linalg.norm(vec) + 1e-12)
            sim = float(np.dot(center_norm, vec_norm))
            scored.append((sim, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_rows = scored[:top_n]

        selected = []
        for sim, row in top_rows:
            selected.append({
                "chain_id": row["chain_id"],
                "paper_id": row["paper_id"],
                "journal": row.get("journal", ""),
                "conclusion_id": row.get("conclusion_id", ""),
                "conclusion_title": row.get("conclusion_title", ""),
                "cluster_id": cid,
                "chain_text": row.get("chain_text", ""),
                "num_steps": row.get("num_steps", 0),
            })
        cluster_selected[cid] = selected
        total_selected += len(selected)

        if (i + 1) % 20 == 0 or i == 0:
            print(f"  [{i+1}/{len(top_ids)}] Cluster {cid}: "
                  f"{len(rows)} -> {len(selected)}, "
                  f"sim range [{top_rows[-1][0]:.4f}, {scored[0][0]:.4f}]",
                  flush=True)

    print(f"  ✓ 选出 {total_selected} 条链, {len(cluster_selected)} 个簇")

    # 5. 下载 xml/md
    print(f"\n[下载] 下载 xml/md 到 {workflows_dir}...", flush=True)
    client = _tos_client()
    bucket = _tos_bucket()
    if not bucket:
        print("ERROR: TOS_BUCKET 未设置")
        return

    total_xml_ok = total_md_ok = 0
    total_xml = total_md = 0
    errors_logged = 0

    for cid in sorted(cluster_selected.keys()):
        chains = cluster_selected[cid]
        cluster_dir = workflows_dir / f"cluster_{cid}"
        xml_dir = cluster_dir / "xml"
        md_dir = cluster_dir / "md"
        xml_dir.mkdir(parents=True, exist_ok=True)
        md_dir.mkdir(parents=True, exist_ok=True)

        with open(cluster_dir / "selected_chains.json", "w", encoding="utf-8") as f:
            json.dump(chains, f, ensure_ascii=False, indent=2)

        xml_tasks = []
        md_tasks = []
        seen_papers = set()

        for chain in chains:
            cid_str = chain["chain_id"]
            pid = chain["paper_id"]
            fs_pid = pid.replace("/", "%2F")

            xml_key = f"{XML_PREFIX}{fs_pid}_reasoning_chain.xml"
            xml_path = xml_dir / f"{cid_str}.xml"
            xml_tasks.append((xml_key, xml_path))

            if pid not in seen_papers:
                seen_papers.add(pid)
                md_path = md_dir / f"{fs_pid}.md"
                md_tasks.append((pid, fs_pid, md_path))

        # 并发下载 XML
        xml_ok = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futs = {pool.submit(_download_file, client, bucket, k, p): k for k, p in xml_tasks}
            for fut in as_completed(futs):
                if fut.result():
                    xml_ok += 1
                elif errors_logged < 5:
                    errors_logged += 1
                    print(f"  ✗ XML: {futs[fut]}", flush=True)

        # 并发下载 MD
        md_ok = 0

        def _dl_md(_pid, fs_pid, md_path):
            for k in [f"{MD_PREFIX}{fs_pid}.md", f"{MD_PREFIX} /{fs_pid}.md"]:
                if _download_file(client, bucket, k, md_path):
                    return True
            return False

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futs = {pool.submit(_dl_md, p, fp, mp): p for p, fp, mp in md_tasks}
            for fut in as_completed(futs):
                if fut.result():
                    md_ok += 1
                elif errors_logged < 5:
                    errors_logged += 1
                    print(f"  ✗ MD: {futs[fut]}", flush=True)

        print(f"  Cluster {cid}: XML {xml_ok}/{len(xml_tasks)}, MD {md_ok}/{len(md_tasks)}", flush=True)
        total_xml_ok += xml_ok
        total_xml += len(xml_tasks)
        total_md_ok += md_ok
        total_md += len(md_tasks)

    print(f"\n[下载] 完成: XML {total_xml_ok}/{total_xml}, MD {total_md_ok}/{total_md}")
    print(f"  输出: {workflows_dir}")


async def main():
    parser = argparse.ArgumentParser(description="通用领域 Step1 流程")
    parser.add_argument("--domain", required=True, help="领域名 (如 materials_science, superconductivity)")
    parser.add_argument("--skip-vectorization", action="store_true", help="跳过向量化，使用已有向量")
    parser.add_argument("--skip-clustering", action="store_true", help="跳过聚类，直接从已有结果下载")
    args = parser.parse_args()

    domain = args.domain
    config = _build_config(domain)

    if args.skip_vectorization:
        config["runtime"]["skip_vectorization"] = True
    if args.skip_clustering:
        config["runtime"]["skip_vectorization"] = True

    d = _domain_dir(domain)
    output_dir = Path(config["data"]["output_dir"])
    lance_db_dir = Path(config["data"]["lance_db_dir"])
    workflows_dir = Path(f"data/{d}/workflows")

    # ── 同步 paper_ids.json → cache ──
    _sync_paper_ids(config)

    if not args.skip_clustering:
        _print_banner(domain, config)

        # ── Step1: 向量化 + 聚类 ──
        result = await run_step1_pipeline_async(config)

        print(f"\n{'='*60}")
        print(f"聚类结果: {result.n_clusters} 个簇")
        if "cluster_size_median" in result.metrics:
            print(f"  大小: min={result.metrics['cluster_size_min']}, "
                  f"median={result.metrics['cluster_size_median']:.0f}, "
                  f"max={result.metrics['cluster_size_max']}")
        if "silhouette" in result.metrics:
            print(f"  Silhouette: {result.metrics['silhouette']:.3f}")
        print(f"{'='*60}")

        # ── 选择代表性样本 ──
        top_percent, max_per_cluster = parse_selection_config(config["clustering"])
        print(f"\n选择策略: 前 {top_percent*100:.0f}% 的簇, 每簇最多 {max_per_cluster} 条链")

        vector_store = LanceVectorStore(
            db_path=lance_db_dir,
            table_name="chain_embeddings"
        )
        selection_result = select_top_clusters(
            vector_store=vector_store,
            centers=result.centers,
            labels=result.labels,
            chain_ids=result.step_ids,
            top_percent=top_percent,
            max_per_cluster=max_per_cluster,
            verbose=True,
        )
        save_selection(selection_result, output_dir)
        vector_store.close()

        print(f"\n✓ 选择完成: {selection_result['summary']['n_clusters_selected']} 个簇, "
              f"{selection_result['summary']['n_chains_selected']} 条链")

    # ── 下载 xml/md ──
    print(f"\n{'='*60}")
    print(f"下载 workflow 文件")
    print(f"{'='*60}")

    download_workflows(
        output_dir=output_dir,
        lance_db_dir=lance_db_dir,
        workflows_dir=workflows_dir,
        top_percent=TOP_PERCENT,
        top_n=TOP_N_PER_CLUSTER,
    )

    print(f"\n{'='*80}")
    print(f"✓ {domain} Step1 全流程完成!")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(main())
