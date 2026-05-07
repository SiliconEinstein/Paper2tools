"""
Step1 主流程 - 串联数据加载→向量化→聚类→保存
"""

import asyncio
import json
from pathlib import Path
from typing import Dict

from .data_loader import load_data_for_step1
from .vectorizer import create_embedder, vectorize_reasoning_chains
from .cluster_metadata import cluster_and_save_to_lance
from ..db import LanceVectorStore
from ..db.schema import CLUSTER_METADATA_SCHEMA


async def run_step1_pipeline_async(config: Dict) -> Dict:
    """
    Step1 主流程入口

    Args:
        config: 配置字典（从 step1_config.yaml 加载）

    Returns:
        Dict: 聚类结果摘要
    """
    print("\n" + "=" * 60, flush=True)
    print("Step1 Pipeline: Text Vectorization & Semantic Clustering", flush=True)
    print("=" * 60, flush=True)

    # 1. 初始化组件
    print("\n[1/5] Initializing components...", flush=True)
    vector_store = LanceVectorStore(
        db_path=Path(config["data"]["lance_db_dir"]),
        table_name="chain_embeddings"
    )
    runtime_cfg = config.get("runtime", {})
    skip_vectorization = bool(runtime_cfg.get("skip_vectorization", False))
    domain = config["data"].get("target_domain", config["data"].get("mode", "unknown"))
    embedder = None
    new_count = 0

    if skip_vectorization:
        print("  ✓ Vector store initialized (skip vectorization mode)", flush=True)
        print("\n[2/5] Loading reasoning chains...", flush=True)
        print("  ↷ Skipped (runtime.skip_vectorization=true)", flush=True)
        print("\n[3/5] Vectorizing reasoning chains...", flush=True)
        print("  ↷ Skipped (reuse existing vectors from LanceDB)", flush=True)
    else:
        embedder = create_embedder(config["vectorizer"])
        print("  ✓ Vector store and embedder initialized", flush=True)

        # 2. 加载数据
        print("\n[2/5] Loading reasoning chains...", flush=True)
        chains = load_data_for_step1(config["data"])
        print(f"  ✓ Loaded {len(chains)} reasoning chains", flush=True)

        # 复制 paper_id_list 到 step1_output（作为正式输出）
        cache_dir = Path(config["data"]["cache_dir"])
        output_dir = Path(config["data"]["output_dir"])
        paper_list_cache = cache_dir / f"paper_ids_{domain}.json"
        paper_list_output = output_dir / f"paper_ids_{domain}.json"

        if paper_list_cache.exists():
            output_dir.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(paper_list_cache, paper_list_output)
            print(f"  ✓ Paper ID list saved to {paper_list_output}", flush=True)

        # 3. 向量化（增量，异步）
        print("\n[3/5] Vectorizing reasoning chains...", flush=True)
        new_count = await vectorize_reasoning_chains(
            chains=chains,
            embedder=embedder,
            vector_store=vector_store,
            domain=domain,
            tos_prefix=config["data"].get("tos_prefix", "paper_ocr"),
            verbose=config["runtime"]["verbose"]
        )
        print(f"  ✓ Vectorized {new_count} new chains", flush=True)

    total = vector_store.count()
    print(f"  ✓ Total vectors in LanceDB: {total}", flush=True)

    # 4. 聚类并保存到 Lance
    print("\n[4/5] Clustering reasoning chains...", flush=True)
    clustering_config = config["clustering"]

    # 初始化聚类元数据存储
    cluster_store = LanceVectorStore(
        db_path=Path(config["data"]["lance_db_dir"]),
        table_name=clustering_config.get("cluster_metadata_table", "cluster_metadata"),
        schema=CLUSTER_METADATA_SCHEMA
    )

    # 执行聚类并保存
    agglomerative_config = clustering_config.get("agglomerative", {})
    labels, n_clusters = cluster_and_save_to_lance(
        vector_store=vector_store,
        cluster_store=cluster_store,
        domain=domain,
        min_pair_sim=agglomerative_config.get("min_pair_sim", 0.6),
        max_size=agglomerative_config.get("max_size", 300),
        auto_evolve=agglomerative_config.get("auto_evolve", True),
        evolve_threshold=agglomerative_config.get("evolve_threshold", 0.6),
        evolve_step=agglomerative_config.get("evolve_step", 0.02),
        verbose=config["runtime"]["verbose"]
    )

    cluster_store.close()
    print(f"  ✓ Clustering complete: {n_clusters} clusters", flush=True)

    # 5. 保存传统格式结果（可选，用于兼容性）
    print("\n[5/5] Saving legacy format results...", flush=True)
    output_dir = Path(config["data"]["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    # 保存简化的聚类结果
    legacy_result = {
        "domain": domain,
        "n_clusters": n_clusters,
        "algorithm": "agglomerative",
        "min_pair_sim": agglomerative_config.get("min_pair_sim", 0.6),
        "total_chains": len(labels)
    }
    with open(output_dir / f"cluster_summary_{domain}.json", "w") as f:
        json.dump(legacy_result, f, indent=2)

    print(f"  ✓ Results saved to {output_dir}", flush=True)

    # 6. 清理
    if embedder is not None:
        await embedder.close()
    vector_store.close()

    print("\n" + "=" * 60, flush=True)
    print("Step1 Pipeline Complete!", flush=True)
    print("=" * 60, flush=True)

    return {
        "domain": domain,
        "n_clusters": n_clusters,
        "total_chains": len(labels),
        "new_vectorized": new_count
    }


def run_step1_pipeline(config: Dict) -> Dict:
    """同步包装器，用于向后兼容"""
    return asyncio.run(run_step1_pipeline_async(config))
