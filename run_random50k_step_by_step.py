#!/usr/bin/env python3
"""
Random 50k 分步测试脚本
每一步独立运行，打印进度，中间结果缓存到本地
"""

import asyncio
import json
import sys
import time
import random
import numpy as np
from pathlib import Path
from datetime import datetime

sys.path.insert(0, '/personal/paper2tools_v2')
sys.path.insert(0, '/personal/paper2tools/src')

# ============================================================
# 配置
# ============================================================
SAMPLE_SIZE = 50000
CACHE_DIR = Path("data/cache_random50k")
OUTPUT_DIR = Path("data/step1_output_random50k")
LANCE_DB_DIR = Path("data/lance_db_random50k")
CHAINS_JSONL = OUTPUT_DIR / "reasoning_chains_random50k.jsonl"
PAPER_IDS_CACHE = CACHE_DIR / "random_sample_50000.json"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LANCE_DB_DIR.mkdir(parents=True, exist_ok=True)


def ts():
    return datetime.now().strftime("%H:%M:%S")


# ============================================================
# Step A: 获取 paper_id 列表（从已有缓存中随机采样）
# ============================================================
def step_a_get_paper_ids():
    """从已有的 bioinformatics paper_id 列表中随机采样 5 万条"""
    if PAPER_IDS_CACHE.exists():
        print(f"[{ts()}] ✓ Paper ID 缓存已存在: {PAPER_IDS_CACHE}")
        with open(PAPER_IDS_CACHE) as f:
            data = json.load(f)
        print(f"[{ts()}]   共 {len(data['paper_ids'])} 个 paper_id")
        return data['paper_ids']

    print(f"[{ts()}] 从已有的 bioinformatics paper_id 列表中随机采样...")

    # 读取已有的 paper_id 列表
    source_file = Path("data/step1_output/paper_ids_bioinformatics.json")
    if not source_file.exists():
        raise FileNotFoundError(f"源文件不存在: {source_file}")

    with open(source_file) as f:
        source_data = json.load(f)

    all_paper_ids = source_data['paper_ids']
    print(f"[{ts()}]   源列表共 {len(all_paper_ids)} 个 paper_id")

    # 随机采样
    random.seed(42)
    if len(all_paper_ids) >= SAMPLE_SIZE:
        sampled = random.sample(all_paper_ids, SAMPLE_SIZE)
        print(f"[{ts()}]   随机采样 {SAMPLE_SIZE} 个")
    else:
        sampled = all_paper_ids
        print(f"[{ts()}]   源列表不足 {SAMPLE_SIZE}，使用全部 {len(sampled)} 个")

    # 保存缓存
    with open(PAPER_IDS_CACHE, 'w') as f:
        json.dump({
            "sample_size": SAMPLE_SIZE,
            "actual_count": len(sampled),
            "source": str(source_file),
            "created_at": datetime.now().isoformat(),
            "paper_ids": sampled
        }, f)
    print(f"[{ts()}] ✓ 保存到 {PAPER_IDS_CACHE}")
    return sampled


# ============================================================
# Step B: 从 TOS 下载 XML 并解析为 ReasoningChain，缓存到 JSONL
# ============================================================
def step_b_download_and_parse(paper_ids):
    """下载 XML 并解析为思维链，保存到 JSONL（支持断点续传）"""
    if CHAINS_JSONL.exists():
        size_mb = CHAINS_JSONL.stat().st_size / 1024 / 1024
        print(f"[{ts()}] ✓ 思维链缓存已存在: {CHAINS_JSONL} ({size_mb:.1f} MB)")
        # 统计行数
        count = sum(1 for _ in open(CHAINS_JSONL))
        print(f"[{ts()}]   共 {count} 条思维链")
        return count

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

    print(f"[{ts()}] 开始从 TOS 下载 {total} 篇论文的 reasoning_chain.xml...")

    with open(CHAINS_JSONL, 'w', encoding='utf-8') as f:
        for i, paper_id in enumerate(paper_ids):
            try:
                xml_content = tos_store.download_reasoning_xml(paper_id)
                if xml_content and xml_content.strip():
                    chains = parse_reasoning_chain_xml(xml_content, paper_id, "random")
                    for chain in chains:
                        from dataclasses import asdict
                        f.write(json.dumps(asdict(chain), ensure_ascii=False) + '\n')
                        total_chains += 1
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1

            # 每 1000 篇打印一次进度
            done = i + 1
            if done % 1000 == 0 or done == total:
                elapsed = time.time() - start_time
                speed = done / elapsed
                eta = (total - done) / speed if speed > 0 else 0
                print(f"[{ts()}]   进度: {done}/{total} ({done*100/total:.1f}%) | "
                      f"成功: {success} | 失败: {failed} | "
                      f"思维链: {total_chains} | "
                      f"速度: {speed:.0f} papers/s | ETA: {eta:.0f}s")

    print(f"[{ts()}] ✓ 下载解析完成: {success} 成功, {failed} 失败, {total_chains} 条思维链")
    return total_chains


# ============================================================
# Step C: 向量化（调用 DashScope Embedding API）
# ============================================================
async def step_c_vectorize():
    """从 JSONL 加载思维链，向量化并写入 LanceDB"""
    from src.step1.data_loader import load_reasoning_chains_from_jsonl
    from src.step1.vectorizer import create_embedder, vectorize_reasoning_chains
    from src.db import LanceVectorStore

    print(f"[{ts()}] 加载思维链...")
    chains = load_reasoning_chains_from_jsonl(CHAINS_JSONL)
    print(f"[{ts()}] ✓ 加载了 {len(chains)} 条思维链")

    print(f"[{ts()}] 初始化 LanceDB 和 Embedder...")
    import yaml
    with open("configs/step1_random50k_config.yaml") as f:
        config = yaml.safe_load(f)

    vector_store = LanceVectorStore(
        db_path=LANCE_DB_DIR,
        table_name="chain_embeddings"
    )
    embedder = create_embedder(config["vectorizer"])

    print(f"[{ts()}] 开始向量化 (chain-level)...")
    new_count = await vectorize_reasoning_chains(
        chains=chains,
        embedder=embedder,
        vector_store=vector_store,
        batch_size=64,
        verbose=True
    )
    print(f"[{ts()}] ✓ 向量化完成: {new_count} 条新向量")

    total = vector_store.count()
    print(f"[{ts()}] ✓ LanceDB 总向量数: {total}")

    await embedder.close()
    vector_store.close()
    return total


# ============================================================
# Step D: 聚类
# ============================================================
def step_d_cluster():
    """对向量进行 HDBSCAN 聚类"""
    from src.step1.clustering import (
        create_clustering_algorithm, cluster_steps,
        save_cluster_results
    )
    from src.db import LanceVectorStore
    import yaml

    with open("configs/step1_random50k_config.yaml") as f:
        config = yaml.safe_load(f)

    print(f"[{ts()}] 打开 LanceDB...")
    vector_store = LanceVectorStore(
        db_path=LANCE_DB_DIR,
        table_name="chain_embeddings"
    )
    total = vector_store.count()
    print(f"[{ts()}] ✓ LanceDB 中有 {total} 条向量")

    print(f"[{ts()}] 开始 HDBSCAN 聚类...")
    algorithm = create_clustering_algorithm(config["clustering"])
    result = cluster_steps(
        vector_store=vector_store,
        algorithm=algorithm,
        umap_config=config["clustering"].get("umap"),
        verbose=True
    )
    print(f"[{ts()}] ✓ 聚类完成: {result.n_clusters} 个簇")

    print(f"[{ts()}] 保存聚类结果...")
    save_cluster_results(result, OUTPUT_DIR)
    print(f"[{ts()}] ✓ 结果保存到 {OUTPUT_DIR}")

    vector_store.close()
    return result


# ============================================================
# Main
# ============================================================
def main():
    print("=" * 60)
    print("Random 50k 分步测试")
    print("=" * 60)

    # Step A
    print(f"\n{'='*40}")
    print(f"[Step A] 获取 paper_id 列表")
    print(f"{'='*40}")
    paper_ids = step_a_get_paper_ids()

    # Step B
    print(f"\n{'='*40}")
    print(f"[Step B] 下载并解析 reasoning_chain.xml")
    print(f"{'='*40}")
    n_chains = step_b_download_and_parse(paper_ids)

    # Step C
    print(f"\n{'='*40}")
    print(f"[Step C] 向量化 (DashScope Embedding API)")
    print(f"{'='*40}")
    n_vectors = asyncio.run(step_c_vectorize())

    # Step D
    print(f"\n{'='*40}")
    print(f"[Step D] 聚类 (HDBSCAN)")
    print(f"{'='*40}")
    result = step_d_cluster()

    print(f"\n{'='*60}")
    print(f"✓ 全部完成!")
    print(f"  思维链: {n_chains}")
    print(f"  向量: {n_vectors}")
    print(f"  聚类: {result.n_clusters} 个簇")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
