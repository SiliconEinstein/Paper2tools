#!/usr/bin/env python3
"""
Random 50k 流式处理：从 bioinformatics paper_id 中随机采样 5 万 → 下载 XML → 向量化 → 聚类
"""

import asyncio
import json
import random
import time
import logging
import numpy as np
import yaml
from pathlib import Path
from datetime import datetime
from dataclasses import asdict

from dotenv import load_dotenv
load_dotenv('/personal/paper2tools_v2/.env')

import sys
sys.path.insert(0, '/personal/paper2tools_v2')
sys.path.insert(0, '/personal/paper2tools/src')

SAMPLE_SIZE = 50000
CACHE_DIR = Path("data/cache_random50k")
OUTPUT_DIR = Path("data/step1_output_random50k")
LANCE_DB_DIR = Path("data/lance_db_random50k")
CHAINS_JSONL = OUTPUT_DIR / "reasoning_chains_random50k.jsonl"
PAPER_IDS_CACHE = CACHE_DIR / "random_sample_50000.json"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LANCE_DB_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")


def ts():
    return datetime.now().strftime("%H:%M:%S")


def get_paper_ids():
    """从 TOS paper_ocr/xml/ 按页读取，收集 5 万个 reasoning_chain.xml 的 paper_id"""
    if PAPER_IDS_CACHE.exists():
        print(f"[{ts()}] ✓ Paper ID 缓存已存在: {PAPER_IDS_CACHE}")
        with open(PAPER_IDS_CACHE) as f:
            data = json.load(f)
        return data['paper_ids']

    print(f"[{ts()}] 从 TOS paper_ocr/xml/ 按页读取，目标 {SAMPLE_SIZE} 个...")

    from staged_lance.storage import LanceTosStore
    from staged_lance.config import StageConfig

    stage_config = StageConfig()
    tos_store = LanceTosStore(stage_config)
    client = tos_store.get_tos_client()

    paper_ids = []
    marker = ""
    page = 0
    suffix = "_reasoning_chain.xml"

    while len(paper_ids) < SAMPLE_SIZE:
        result = client.list_objects(
            stage_config.tos_bucket,
            prefix=stage_config.tos_xml_source_prefix,
            marker=marker
        )
        contents = getattr(result, "contents", None) or []
        if not contents:
            break

        page += 1
        for item in contents:
            key = getattr(item, "key", "") or ""
            if not key.endswith(suffix):
                continue
            base = key.split("/")[-1]
            pid = base[: -len(suffix)]
            if pid:
                paper_ids.append(pid)
                if len(paper_ids) >= SAMPLE_SIZE:
                    break

        if len(paper_ids) % 5000 < 100:
            print(f"[{ts()}]   page {page}: 已收集 {len(paper_ids)} 个 paper_id")

        if not getattr(result, "is_truncated", False):
            break
        marker = getattr(result, "next_marker", "") or ""

    print(f"[{ts()}] ✓ 收集完成: {len(paper_ids)} 个 paper_id ({page} 页)")

    with open(PAPER_IDS_CACHE, 'w') as f:
        json.dump({
            "sample_size": SAMPLE_SIZE,
            "actual_count": len(paper_ids),
            "source": "TOS paper_ocr/xml/ pagination",
            "created_at": datetime.now().isoformat(),
            "paper_ids": paper_ids
        }, f)

    return paper_ids


def download_and_parse(paper_ids):
    """下载 XML 并解析为 JSONL（断点续传）"""
    if CHAINS_JSONL.exists():
        existing_count = sum(1 for _ in open(CHAINS_JSONL))
        print(f"[{ts()}] ✓ JSONL 已存在: {CHAINS_JSONL} ({existing_count} 条)")
        return existing_count

    from staged_lance.storage import LanceTosStore
    from staged_lance.config import StageConfig
    from src.step1.data_loader import parse_reasoning_chain_xml

    stage_config = StageConfig()
    tos_store = LanceTosStore(stage_config)

    total = len(paper_ids)
    success = 0
    failed = 0
    total_chains = 0
    start_time = time.time()

    print(f"[{ts()}] 开始下载 {total} 篇论文的 reasoning_chain.xml...")

    with open(CHAINS_JSONL, 'w', encoding='utf-8') as f:
        for i, paper_id in enumerate(paper_ids):
            try:
                xml_content = tos_store.download_reasoning_xml(paper_id)
                if xml_content and xml_content.strip():
                    chains = parse_reasoning_chain_xml(xml_content, paper_id, "random")
                    for chain in chains:
                        f.write(json.dumps(asdict(chain), ensure_ascii=False) + '\n')
                        total_chains += 1
                    success += 1
                else:
                    failed += 1
            except Exception as exc:
                if failed < 5:  # 只记录前5个错误
                    print(f"[{ts()}] ERROR downloading {paper_id}: {exc}")
                failed += 1

            if (i + 1) % 1000 == 0 or (i + 1) == total:
                elapsed = time.time() - start_time
                speed = (i + 1) / elapsed
                eta = (total - i - 1) / speed if speed > 0 else 0
                print(
                    f"[{ts()}]   {i+1}/{total} ({(i+1)*100/total:.1f}%) | "
                    f"成功: {success} | 失败: {failed} | "
                    f"思维链: {total_chains} | "
                    f"速度: {speed:.0f} papers/s | ETA: {eta:.0f}s"
                )

    print(f"[{ts()}] ✓ 下载完成: {success} 成功, {failed} 失败, {total_chains} 条思维链")
    return total_chains


def iter_chains_from_jsonl(jsonl_path: Path, chunk_size: int = 5000):
    """流式读取 JSONL"""
    chunk = []
    count = 0
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            d = json.loads(line)
            chain_id = f"{d['paper_id']}_{d['conclusion_id']}"
            steps = d['steps']
            chain_text = "\n".join(f"Step {s['step_id']}: {s['text']}" for s in steps)

            metadata = {
                "paper_id": d['paper_id'],
                "journal": d.get('journal', ''),
                "conclusion_id": d['conclusion_id'],
                "conclusion_title": d.get('conclusion_title', ''),
                "chain_text": chain_text[:2000],
                "cluster_id": -1,
                "num_steps": len(steps),
                "has_citations": any(s.get('has_citations', False) for s in steps),
                "has_figures": any(s.get('has_figures', False) for s in steps),
            }
            chunk.append((chain_id, chain_text, metadata))
            count += 1

            if len(chunk) >= chunk_size:
                yield chunk, count
                chunk = []

    if chunk:
        yield chunk, count


async def vectorize_and_cluster():
    """向量化 + 聚类"""
    with open("configs/step1_random50k_config.yaml") as f:
        config = yaml.safe_load(f)

    from src.step1.vectorizer import DashScopeEmbedder
    from src.db import LanceVectorStore

    vector_store = LanceVectorStore(db_path=LANCE_DB_DIR, table_name="chain_embeddings")
    embedder = DashScopeEmbedder(config["vectorizer"])

    try:
        existing_ids = set(vector_store.table.to_arrow().column("chain_id").to_pylist())
    except Exception:
        existing_ids = set()

    total_chains = sum(1 for _ in open(CHAINS_JSONL))
    print(f"[{ts()}] JSONL 共 {total_chains} 条思维链")
    print(f"[{ts()}] LanceDB 已有 {len(existing_ids)} 条向量\n")

    chunk_size = 5000
    n_chunks = (total_chains + chunk_size - 1) // chunk_size
    total_success = 0
    total_failed = 0
    total_skipped = 0
    pipeline_start = time.monotonic()
    chunk_times = []

    print(f"[{ts()}] 开始向量化: {n_chunks} 个 chunk\n")

    for chunk_items, _ in iter_chains_from_jsonl(CHAINS_JSONL, chunk_size):
        chunk_idx = len(chunk_times)
        chunk_start = time.monotonic()

        new_items = [(cid, text, meta) for cid, text, meta in chunk_items if cid not in existing_ids]
        skipped = len(chunk_items) - len(new_items)
        total_skipped += skipped

        if not new_items:
            chunk_times.append(0.01)
            print(f"  Chunk {chunk_idx+1}/{n_chunks}: all {len(chunk_items)} skipped")
            continue

        results = {}
        failed_ids = []

        async def on_result(chain_id, vector, metadata):
            results[chain_id] = (vector, metadata)

        async def on_error(chain_id, exc):
            failed_ids.append(chain_id)

        await embedder.embed_batch(new_items, on_result, on_error)

        for cid, (vector, meta) in results.items():
            vector_store.add_vectors([cid], np.array([vector], dtype=np.float32), [meta])
            existing_ids.add(cid)
        vector_store.flush()

        chunk_success = len(results)
        chunk_failed = len(failed_ids)
        total_success += chunk_success
        total_failed += chunk_failed

        chunk_elapsed = time.monotonic() - chunk_start
        chunk_times.append(chunk_elapsed)
        avg_time = sum(chunk_times) / len(chunk_times)
        remaining = n_chunks - chunk_idx - 1
        eta_min = (avg_time * remaining) / 60
        rps = chunk_success / chunk_elapsed if chunk_elapsed > 0 else 0

        print(
            f"  Chunk {chunk_idx+1}/{n_chunks}: "
            f"{chunk_success} ok, {chunk_failed} fail, {skipped} skip | "
            f"{chunk_elapsed:.0f}s ({rps:.0f} RPS) | "
            f"total {total_success}/{total_chains} | "
            f"ETA {eta_min:.0f}min"
        )

    await embedder.close()

    total_elapsed = time.monotonic() - pipeline_start
    rps_avg = total_success / total_elapsed if total_elapsed > 0 else 0
    print(f"\n[{ts()}] ✓ 向量化完成: {total_elapsed:.0f}s")
    print(f"  Success: {total_success} | Failed: {total_failed} | Skipped: {total_skipped}")
    print(f"  Avg RPS: {rps_avg:.1f}")

    # 聚类
    total_vectors = vector_store.count()
    print(f"\n[{ts()}] [聚类] LanceDB 中有 {total_vectors} 条向量")

    if total_vectors < 10:
        print("向量太少，跳过聚类")
        vector_store.close()
        return

    print(f"[{ts()}] 开始 KMeans 聚类 (k={config['clustering']['n_clusters']})...")
    from src.step1.clustering import create_clustering_algorithm, cluster_steps, save_cluster_results
    from src.step1.cluster_selector import select_top_clusters, save_selection

    algorithm = create_clustering_algorithm(config["clustering"])
    result = cluster_steps(vector_store=vector_store, algorithm=algorithm, umap_config=config["clustering"].get("umap"), verbose=True)
    print(f"[{ts()}] ✓ 聚类完成: {result.n_clusters} 个簇")

    save_cluster_results(result, OUTPUT_DIR)
    print(f"[{ts()}] ✓ 聚类结果保存到 {OUTPUT_DIR}")

    # 选择 top 10% 簇，每簇取离中心最近的 10 个点
    print(f"\n[{ts()}] 选择 top 10% 簇...")
    selection = select_top_clusters(
        vector_store=vector_store,
        centers=result.centers,
        labels=result.labels,
        chain_ids=result.step_ids,
        top_percent=0.1,
        max_per_cluster=10,
        verbose=True
    )
    save_selection(selection, OUTPUT_DIR)
    print(f"[{ts()}] ✓ 选择结果保存到 {OUTPUT_DIR}")

    vector_store.close()


async def main():
    print("=" * 60)
    print("Random 50k 流式处理")
    print("=" * 60)

    # Step A: 获取 paper_id
    print(f"\n[Step A] 获取 paper_id 列表")
    paper_ids = get_paper_ids()

    # Step B: 下载并解析
    print(f"\n[Step B] 下载并解析 reasoning_chain.xml")
    n_chains = download_and_parse(paper_ids)

    # Step C+D: 向量化 + 聚类
    print(f"\n[Step C+D] 向量化 + 聚类")
    await vectorize_and_cluster()

    print(f"\n{'='*60}\n✓ Random 50k 全部完成!\n{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
