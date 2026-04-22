#!/usr/bin/env python3
"""
Journal embedding + clustering：流式读取 + 分 chunk 向量化，内存恒定
"""

import asyncio
import json
import time
import logging
import numpy as np
import yaml
from pathlib import Path
from datetime import datetime

import sys
sys.path.insert(0, '/personal/paper2tools_v2')

CHAINS_JSONL = Path("data/step1_output/reasoning_chains_bioinformatics.jsonl")
LANCE_DB_DIR = Path("data/lance_db")
OUTPUT_DIR = Path("data/step1_output")
CONFIG_PATH = Path("configs/step1_config.yaml")

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")


def ts():
    return datetime.now().strftime("%H:%M:%S")


def iter_chains_from_jsonl(jsonl_path: Path, chunk_size: int = 5000):
    """流式读取 JSONL，按 chunk 产出 (chain_id, chain_text, metadata) 列表。
    内存中同时只保留一个 chunk。"""
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


def count_lines(path: Path) -> int:
    """快速统计行数"""
    n = 0
    with open(path, 'rb') as f:
        for _ in f:
            n += 1
    return n


async def main():
    print("=" * 60)
    print("Journal Embedding + Clustering (Streaming)")
    print("=" * 60)

    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    # 统计总行数
    print(f"[{ts()}] 统计 JSONL 行数...")
    total_chains = count_lines(CHAINS_JSONL)
    print(f"[{ts()}] ✓ 共 {total_chains} 条思维链")

    # 初始化
    from src.step1.vectorizer import DashScopeEmbedder
    from src.db import LanceVectorStore

    vector_store = LanceVectorStore(db_path=LANCE_DB_DIR, table_name="chain_embeddings")
    embedder = DashScopeEmbedder(config["vectorizer"])

    # 检查已有向量
    try:
        existing_ids = set(vector_store.table.to_arrow().column("chain_id").to_pylist())
    except Exception:
        existing_ids = set()
    print(f"[{ts()}] LanceDB 已有 {len(existing_ids)} 条向量")

    # 流式向量化
    chunk_size = 5000
    n_chunks = (total_chains + chunk_size - 1) // chunk_size
    total_success = 0
    total_failed = 0
    total_skipped = 0
    pipeline_start = time.monotonic()
    chunk_times = []

    print(f"[{ts()}] 开始向量化: {n_chunks} 个 chunk, 每 chunk {chunk_size} 条\n")

    for chunk_items, cumulative_read in iter_chains_from_jsonl(CHAINS_JSONL, chunk_size):
        chunk_idx = len(chunk_times)
        chunk_start = time.monotonic()

        # 过滤已存在的
        new_items = [(cid, text, meta) for cid, text, meta in chunk_items if cid not in existing_ids]
        skipped = len(chunk_items) - len(new_items)
        total_skipped += skipped

        if not new_items:
            chunk_times.append(0.01)
            print(f"  Chunk {chunk_idx+1}/{n_chunks}: all {len(chunk_items)} skipped (exist)")
            continue

        # Worker pool 向量化
        results = {}
        failed_ids = []

        async def on_result(chain_id, vector, metadata):
            results[chain_id] = (vector, metadata)

        async def on_error(chain_id, exc):
            failed_ids.append(chain_id)

        await embedder.embed_batch(new_items, on_result, on_error)

        # 写入 LanceDB
        for cid, (vector, meta) in results.items():
            vector_store.add_vectors([cid], np.array([vector], dtype=np.float32), [meta])
            existing_ids.add(cid)  # 更新已存在集合
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
    print(f"\n{'='*60}\n✓ 全部完成!\n{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
