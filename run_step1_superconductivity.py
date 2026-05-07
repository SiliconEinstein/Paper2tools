#!/usr/bin/env python3
"""
超导领域 Step1 流程：向量化 + HDBSCAN 聚类 + 选择代表性样本

与本领域需求一致：用**密度聚类、自动簇数**，避免 K-Means 固定 K 与球形假设把新方法
**强行并入**不合适的簇。全量大规模下 HDBSCAN 较慢是预期；加速需另做工程化（子采样、
降维后再聚类等），而不是改用 K-Means。

用法:
    cd paper2tools_v2 && python run_step1_superconductivity.py

注意:
    ``load_data_for_step1`` 只认 ``data/Superconductivity/cache/paper_ids_superconductivity.json``。
    若你把列表放在 ``step1_output/paper_ids_superconductivity.json``，本脚本会在启动时
    自动同步到 cache（后者更新或 cache 不存在时）。
"""

import asyncio
import os
import shutil
import yaml
from pathlib import Path

REPO = Path(__file__).resolve().parent
os.chdir(REPO)

from src.step1.pipeline import run_step1_pipeline_async
from src.step1.clustering import select_top_clusters, save_selection, parse_selection_config
from src.db import LanceVectorStore


def _print_clustering_banner(clustering: dict) -> None:
    """按算法打印关键参数，避免 kmeans 时仍读 hdbscan 字段。"""
    algo = str(clustering.get("algorithm", "")).lower()
    print(f"聚类算法: {algo.upper()}")
    if algo == "hdbscan":
        h = clustering.get("hdbscan") or {}
        print(f"  - min_cluster_size: {h.get('min_cluster_size')}")
        print(f"  - min_samples: {h.get('min_samples')}")
        print(f"  - metric: {h.get('metric')}")
        print(f"  - cluster_selection_method: {h.get('cluster_selection_method')}")
    elif algo == "kmeans":
        print(f"  - n_clusters: {clustering.get('n_clusters')}")
        print(f"  - mini_batch: {clustering.get('mini_batch', True)}")
        print(f"  - batch_size: {clustering.get('batch_size', 10000)}")
        print(f"  - device: {clustering.get('device', 'cpu')}")
    elif algo == "agglomerative":
        print(f"  - device: {clustering.get('device', 'cpu')}（agglomerative 主体在 CPU）")
    else:
        print(f"  - （详见 configs 中 clustering 段）")


def _sync_paper_ids_list(config: dict) -> None:
    """与 data_loader 一致：论文列表必须在 cache_dir；若仅维护在 step1_output 则拷贝过去。"""
    data = config["data"]
    domain = data.get("target_domain", "superconductivity")
    cache_dir = Path(data["cache_dir"])
    output_dir = Path(data["output_dir"])
    name = f"paper_ids_{domain}.json"
    src_out = output_dir / name
    dst_cache = cache_dir / name
    if not src_out.is_file():
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    if not dst_cache.is_file() or src_out.stat().st_mtime > dst_cache.stat().st_mtime:
        shutil.copy2(src_out, dst_cache)
        print(f"[paper_ids] 已同步: {src_out} → {dst_cache}", flush=True)


async def main():
    # 加载配置
    config_path = Path("configs/step1_superconductivity_config.yaml")
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    _sync_paper_ids_list(config)

    print(f"\n{'='*80}")
    print(f"超导领域 Step1: 向量化 + HDBSCAN + 样本选择")
    print(f"{'='*80}")
    print(f"\n配置文件: {config_path}")
    print(f"目标领域: {config['data']['target_domain']}")
    _print_clustering_banner(config["clustering"])
    print(f"\n输出目录: {config['data']['output_dir']}")
    print(f"向量库: {config['data']['lance_db_dir']}")
    print(f"{'='*80}\n")

    # 运行 Step1 聚类流程
    result = await run_step1_pipeline_async(config)

    # 打印聚类结果摘要
    print(f"\n{'='*80}")
    print(f"聚类结果摘要")
    print(f"{'='*80}")
    print(f"发现簇数量: {result.n_clusters}")
    print(f"噪声点数量: {result.metrics.get('n_noise', 0)}")
    print(f"噪声点比例: {result.metrics.get('noise_ratio', 0):.1%}")

    if 'cluster_size_median' in result.metrics:
        print(f"\n簇大小统计:")
        print(f"  最小: {result.metrics['cluster_size_min']}")
        print(f"  中位数: {result.metrics['cluster_size_median']:.0f}")
        print(f"  平均: {result.metrics['cluster_size_mean']:.0f}")
        print(f"  最大: {result.metrics['cluster_size_max']}")

    if 'silhouette' in result.metrics:
        print(f"\n聚类质量指标:")
        print(f"  Silhouette Score: {result.metrics['silhouette']:.3f}")
        print(f"  Calinski-Harabasz: {result.metrics.get('calinski_harabasz', 0):.1f}")
        if 'davies_bouldin' in result.metrics:
            print(f"  Davies-Bouldin: {result.metrics['davies_bouldin']:.4f}")

    print(f"\n{'='*80}")
    print(f"✓ 聚类完成！结果已保存到 {config['data']['output_dir']}")
    print(f"{'='*80}\n")

    # 选择代表性样本
    print(f"\n{'='*80}")
    print(f"选择代表性样本")
    print(f"{'='*80}")

    top_percent, max_per_cluster = parse_selection_config(config['clustering'])
    print(f"选择策略: 前 {top_percent*100:.0f}% 的簇，每簇最多 {max_per_cluster} 个样本（距质心最近）")

    vector_store = LanceVectorStore(
        db_path=Path(config["data"]["lance_db_dir"]),
        table_name="chain_embeddings"
    )

    selection_result = select_top_clusters(
        vector_store=vector_store,
        centers=result.centers,
        labels=result.labels,
        chain_ids=result.step_ids,
        top_percent=top_percent,
        max_per_cluster=max_per_cluster,
        verbose=True
    )

    output_dir = Path(config['data']['output_dir'])
    save_selection(selection_result, output_dir)

    print(f"\n✓ 选择完成！")
    print(f"  选中簇数: {selection_result['summary']['n_clusters_selected']}")
    print(f"  选中样本数: {selection_result['summary']['n_chains_selected']}")
    print(f"{'='*80}\n")

    vector_store.close()

    print(f"\n{'='*80}")
    print(f"✓ Step1 全流程完成！")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(main())
