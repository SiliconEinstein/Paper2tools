"""
Step1 主流程 - 串联数据加载→向量化→聚类→保存
"""

import asyncio
import numpy as np
from pathlib import Path
from typing import Dict

from .data_loader import load_data_for_step1
from .vectorizer import create_embedder, vectorize_reasoning_chains
from .clustering import (
    create_clustering_algorithm,
    cluster_steps,
    find_optimal_k,
    save_cluster_results,
    ClusterResult
)
from ..db import LanceVectorStore


def read_all_vectors_from_store(vector_store: LanceVectorStore) -> np.ndarray:
    """从 LanceDB 读取所有向量"""
    arrow_table = vector_store.table.to_arrow()
    vectors = np.array(arrow_table.column("vector").to_pylist(), dtype=np.float32)
    return vectors


async def run_step1_pipeline_async(config: Dict) -> ClusterResult:
    """
    Step1 主流程入口

    Args:
        config: 配置字典（从 step1_config.yaml 加载）

    Returns:
        ClusterResult: 聚类结果
    """
    print("\n" + "=" * 60)
    print("Step1 Pipeline: Text Vectorization & Semantic Clustering")
    print("=" * 60)

    # 1. 初始化组件
    print("\n[1/5] Initializing components...")
    vector_store = LanceVectorStore(
        db_path=Path(config["data"]["lance_db_dir"]),
        table_name="chain_embeddings"
    )
    embedder = create_embedder(config["vectorizer"])
    print("  ✓ Vector store and embedder initialized")

    # 2. 加载数据
    print("\n[2/5] Loading reasoning chains...")
    chains = load_data_for_step1(config["data"])
    print(f"  ✓ Loaded {len(chains)} reasoning chains")

    # 复制 paper_id_list 到 step1_output（作为正式输出）
    cache_dir = Path(config["data"]["cache_dir"])
    output_dir = Path(config["data"]["output_dir"])
    domain = config["data"].get("target_domain", config["data"].get("mode", "unknown"))
    paper_list_cache = cache_dir / f"paper_ids_{domain}.json"
    paper_list_output = output_dir / f"paper_ids_{domain}.json"

    if paper_list_cache.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(paper_list_cache, paper_list_output)
        print(f"  ✓ Paper ID list saved to {paper_list_output}")

    # 3. 向量化（增量，异步）
    print("\n[3/5] Vectorizing reasoning chains...")
    new_count = await vectorize_reasoning_chains(
        chains=chains,
        embedder=embedder,
        vector_store=vector_store,
        verbose=config["runtime"]["verbose"]
    )
    print(f"  ✓ Vectorized {new_count} new chains")

    total = vector_store.count()
    print(f"  ✓ Total vectors in LanceDB: {total}")

    # 4. 聚类
    print("\n[4/5] Clustering reasoning chains...")
    clustering_config = config["clustering"].copy()

    # 如果 kmeans + n_clusters=null，先搜索最优 k
    if clustering_config["algorithm"] == "kmeans" and clustering_config.get("n_clusters") is None:
        print("  Auto-selecting optimal k...")
        vectors = read_all_vectors_from_store(vector_store)
        optimal_k = find_optimal_k(
            vectors,
            min_k=clustering_config["auto_k"]["min_k"],
            max_k=clustering_config["auto_k"]["max_k"],
            method=clustering_config["auto_k"]["method"]
        )
        print(f"  ✓ Auto-selected k={optimal_k}")
        clustering_config["n_clusters"] = optimal_k

    algorithm = create_clustering_algorithm(clustering_config)

    result = cluster_steps(
        vector_store=vector_store,
        algorithm=algorithm,
        umap_config=clustering_config.get("umap"),
        verbose=config["runtime"]["verbose"]
    )
    print(f"  ✓ Clustering complete: {result.n_clusters} clusters")

    # 5. 保存结果
    print("\n[5/5] Saving results...")
    output_dir = Path(config["data"]["output_dir"])
    save_cluster_results(result, output_dir)
    print(f"  ✓ Results saved to {output_dir}")

    # 6. 清理
    await embedder.close()
    vector_store.close()

    print("\n" + "=" * 60)
    print("Step1 Pipeline Complete!")
    print("=" * 60)

    return result


def run_step1_pipeline(config: Dict) -> ClusterResult:
    """同步包装器，用于向后兼容"""
    return asyncio.run(run_step1_pipeline_async(config))
