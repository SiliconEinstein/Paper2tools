#!/usr/bin/env python3
"""
为每个 top 10% cluster 选择离簇中心最近的 50 条思维链，
下载对应的 xml 和 md 文件，输出格式参考 data/workflows_100/cluster_1516。

输出结构:
  data/Superconductivity/workflows_top50/cluster_{id}/
    ├── selected_chains.json   # 50 条链（含 chain_text, journal 等完整字段）
    ├── xml/
    │   └── {chain_id}.xml
    └── md/
        └── {paper_id}.md
"""
import json
import os
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import lancedb
import numpy as np
import tos
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ── 路径配置 ──────────────────────────────────────────────
STEP1_DIR = Path("data/Superconductivity/step1_output_agglomerative_v2")
CLUSTER_CENTERS_PATH = STEP1_DIR / "cluster_centers.npy"
CLUSTER_LABELS_PATH = STEP1_DIR / "cluster_labels.json"
CLUSTER_STATS_PATH = STEP1_DIR / "cluster_stats.json"
LANCE_DB_PATH = Path("data/Superconductivity/lance_db")
OUTPUT_BASE = Path("data/Superconductivity/workflows_top50")

TOP_N = 50            # 每个簇选多少条链
TOP_PERCENT = 0.10    # 选前多少比例的簇
MAX_WORKERS = 10      # TOS 下载并发数

# ── TOS 配置 ──────────────────────────────────────────────
XML_PREFIX = "paper_ocr/xml/"
MD_PREFIX = "paper_ocr/md/"


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


def download_file(client, bucket, key, local_path: Path) -> bool:
    try:
        obj = client.get_object(bucket, key)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(obj.read())
        return True
    except Exception:
        return False


def get_top_cluster_ids() -> list[int]:
    """根据 cluster_sizes 选出前 TOP_PERCENT 的簇 ID"""
    with open(CLUSTER_STATS_PATH) as f:
        stats = json.load(f)
    sizes = stats["cluster_sizes"]  # {str(cluster_id): count}
    sorted_ids = sorted(sizes.keys(), key=lambda k: sizes[k], reverse=True)
    n = max(1, int(len(sorted_ids) * TOP_PERCENT))
    return [int(cid) for cid in sorted_ids[:n]]


def main():
    print("=== 选择每簇最近 50 条链并下载文件 ===\n")

    # 1. 确定目标簇
    top_ids = get_top_cluster_ids()
    print(f"[1/5] 目标簇: {len(top_ids)} 个 (top {TOP_PERCENT*100:.0f}%)")

    # 2. 加载簇中心
    centers = np.load(CLUSTER_CENTERS_PATH)  # (n_clusters, dim)
    print(f"[2/5] 加载 cluster_centers: {centers.shape}")

    # 3. 加载 cluster_labels.json，按 cluster_id 分组 chain_id
    print(f"[3/5] 加载 cluster_labels 并分组...", flush=True)
    with open(CLUSTER_LABELS_PATH) as f:
        labels = json.load(f)  # {chain_id: cluster_id}

    top_ids_set = set(top_ids)
    cluster_to_chain_ids: dict[int, list[str]] = {cid: [] for cid in top_ids}
    for chain_id, cluster_id in labels.items():
        if cluster_id in top_ids_set:
            cluster_to_chain_ids[cluster_id].append(chain_id)
    print(f"  ✓ 共 {sum(len(v) for v in cluster_to_chain_ids.values())} 条链分布在 {len(cluster_to_chain_ids)} 个目标簇")

    print(f"  从 LanceDB 读取链数据 (按 chain_id 批量查询)...", flush=True)
    db = lancedb.connect(str(LANCE_DB_PATH))
    table = db.open_table("chain_embeddings")

    cluster_selected: dict[int, list[dict]] = {}
    total_selected = 0

    for i, cid in enumerate(sorted(top_ids)):
        chain_ids = cluster_to_chain_ids[cid]
        if not chain_ids:
            continue

        # LanceDB IN 查询：构造引号字符串
        # 分批查询避免 SQL 过长
        rows = []
        BATCH = 1000
        for j in range(0, len(chain_ids), BATCH):
            batch_ids = chain_ids[j:j+BATCH]
            id_list = ",".join(f"'{x}'" for x in batch_ids)
            sub = (
                table.search()
                .where(f"chain_id IN ({id_list})")
                .limit(BATCH * 2)
                .to_list()
            )
            rows.extend(sub)
        if not rows:
            print(f"  Cluster {cid}: 0 rows in LanceDB, skipping")
            continue

        # 提取向量并计算到簇中心的余弦距离
        center = centers[cid]
        center_norm = center / (np.linalg.norm(center) + 1e-12)

        distances = []
        for row in rows:
            vec = np.array(row["vector"], dtype=np.float32)
            vec_norm = vec / (np.linalg.norm(vec) + 1e-12)
            cos_sim = float(np.dot(center_norm, vec_norm))
            distances.append((cos_sim, row))

        # 按余弦相似度降序，取 top N
        distances.sort(key=lambda x: x[0], reverse=True)
        top_rows = distances[:TOP_N]

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
                  f"{len(rows)} chains -> selected {len(selected)}, "
                  f"top sim={distances[0][0]:.4f}, cutoff sim={top_rows[-1][0]:.4f}",
                  flush=True)

    print(f"  总计选出 {total_selected} 条链, 涉及 {len(cluster_selected)} 个簇")

    # 4. 写 selected_chains.json + 下载文件
    print(f"\n[4/5] 写入 selected_chains.json 并下载 xml/md...", flush=True)

    client = _tos_client()
    bucket = _tos_bucket()
    if not bucket:
        print("ERROR: TOS_BUCKET 未设置")
        return

    total_xml_ok = 0
    total_xml_total = 0
    total_md_ok = 0
    total_md_total = 0
    errors_logged = 0

    for cid in sorted(cluster_selected.keys()):
        chains = cluster_selected[cid]
        cluster_dir = OUTPUT_BASE / f"cluster_{cid}"
        xml_dir = cluster_dir / "xml"
        md_dir = cluster_dir / "md"
        xml_dir.mkdir(parents=True, exist_ok=True)
        md_dir.mkdir(parents=True, exist_ok=True)

        # 写 selected_chains.json
        with open(cluster_dir / "selected_chains.json", "w", encoding="utf-8") as f:
            json.dump(chains, f, ensure_ascii=False, indent=2)

        # 收集下载任务
        xml_tasks = []  # (key, local_path)
        md_tasks = []
        seen_papers = set()

        for chain in chains:
            cid_str = chain["chain_id"]
            pid = chain["paper_id"]
            fs_pid = pid.replace("/", "%2F")

            # XML: {paper_id}_reasoning_chain.xml -> 存为 {chain_id}.xml
            xml_key = f"{XML_PREFIX}{fs_pid}_reasoning_chain.xml"
            xml_path = xml_dir / f"{cid_str}.xml"
            xml_tasks.append((xml_key, xml_path))

            # MD: 每个 paper 只下一次
            if pid not in seen_papers:
                seen_papers.add(pid)
                md_path = md_dir / f"{fs_pid}.md"
                md_tasks.append((pid, fs_pid, md_path))

        # 并发下载 XML
        xml_ok = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futs = {
                pool.submit(download_file, client, bucket, key, path): key
                for key, path in xml_tasks
            }
            for fut in as_completed(futs):
                if fut.result():
                    xml_ok += 1
                elif errors_logged < 5:
                    errors_logged += 1
                    print(f"  ✗ XML 下载失败: {futs[fut]}", flush=True)

        # 并发下载 MD（尝试两种路径格式）
        md_ok = 0

        def _download_md(pid, fs_pid, md_path):
            candidates = [
                f"{MD_PREFIX}{fs_pid}.md",
                f"{MD_PREFIX} /{fs_pid}.md",
            ]
            for k in candidates:
                if download_file(client, bucket, k, md_path):
                    return True
            return False

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futs = {
                pool.submit(_download_md, pid, fs_pid, path): pid
                for pid, fs_pid, path in md_tasks
            }
            for fut in as_completed(futs):
                if fut.result():
                    md_ok += 1
                elif errors_logged < 5:
                    errors_logged += 1
                    print(f"  ✗ MD 下载失败: {futs[fut]}", flush=True)

        print(f"  Cluster {cid}: XML {xml_ok}/{len(xml_tasks)}, MD {md_ok}/{len(md_tasks)}", flush=True)
        total_xml_ok += xml_ok
        total_xml_total += len(xml_tasks)
        total_md_ok += md_ok
        total_md_total += len(md_tasks)

    # 5. 汇总
    print(f"\n[5/5] 完成!")
    print("=" * 60)
    print(f"  簇数: {len(cluster_selected)}")
    print(f"  链数: {total_selected}")
    print(f"  XML: {total_xml_ok}/{total_xml_total}")
    print(f"  MD:  {total_md_ok}/{total_md_total}")
    print(f"  输出: {OUTPUT_BASE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
