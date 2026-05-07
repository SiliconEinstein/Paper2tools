"""
聚类结果可视化 - 对比期刊聚类 vs 随机50k聚类
"""

import json
import numpy as np
from pathlib import Path
from typing import Optional
from collections import Counter

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.decomposition import PCA


def load_cluster_data(output_dir: Path) -> dict:
    """加载聚类结果"""
    labels_path = output_dir / "cluster_labels.json"
    stats_path = output_dir / "cluster_stats.json"

    with open(labels_path, 'r') as f:
        labels_map = json.load(f)
    with open(stats_path, 'r') as f:
        stats = json.load(f)

    return {"labels_map": labels_map, "stats": stats}


def plot_cluster_stats_summary(
    output_dir: Path,
    output_path: Path,
    title: str = "Step1 clustering",
):
    """从 cluster_stats.json（优先用 cluster_sizes）生成统计图，避免读取巨大 labels JSON。"""
    stats_path = output_dir / "cluster_stats.json"
    with open(stats_path, "r") as f:
        stats = json.load(f)

    cs_raw = stats.get("cluster_sizes")
    if cs_raw:
        cluster_sizes = Counter({int(k): int(v) for k, v in cs_raw.items()})
    else:
        data = load_cluster_data(output_dir)
        cluster_sizes = Counter(data["labels_map"].values())

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5))
    fig.suptitle(title, fontsize=14, fontweight="bold")

    valid_sizes = sorted([v for k, v in cluster_sizes.items() if k >= 0], reverse=True)
    n_noise = cluster_sizes.get(-1, 0)

    ax = axes[0]
    ax.bar(range(len(valid_sizes)), valid_sizes, color="steelblue", alpha=0.7)
    ax.set_title("Cluster size distribution")
    ax.set_xlabel("Cluster (sorted by size, desc)")
    ax.set_ylabel("Number of steps")
    ax.text(
        0.95,
        0.95,
        f"Clusters: {len(valid_sizes)}\nNoise: {n_noise}",
        transform=ax.transAxes,
        ha="right",
        va="top",
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
    )

    ax = axes[1]
    if valid_sizes:
        sorted_sizes = sorted(valid_sizes)
        cumulative = np.cumsum(sorted_sizes) / sum(sorted_sizes)
        ax.plot(range(len(sorted_sizes)), cumulative, "b-", linewidth=2)
        ax.set_title("CDF of cluster sizes")
        ax.set_xlabel("Cluster (sorted by size, asc)")
        ax.set_ylabel("Cumulative proportion")
        ax.axhline(y=0.9, color="r", linestyle="--", alpha=0.5, label="90%")
        ax.legend()

    ax = axes[2]
    metrics = stats.get("metrics", {})
    metric_names = ["silhouette", "calinski_harabasz", "davies_bouldin"]
    metric_values = [metrics.get(m, 0) for m in metric_names]
    bars = ax.barh(metric_names, metric_values, color=["green", "blue", "red"], alpha=0.7)
    ax.set_title("Clustering quality metrics")
    for bar, val in zip(bars, metric_values):
        ax.text(
            bar.get_width() + 0.01 * (abs(bar.get_width()) + 1e-6),
            bar.get_y() + bar.get_height() / 2,
            f"{val:.4f}",
            va="center",
        )

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved stats summary to {output_path}")


def plot_cluster_centers_pca(
    centers_npy: Path,
    output_path: Path,
    title: str = "KMeans cluster centers (PCA 2D)",
):
    """对聚类中心向量做 PCA 2D 散点（轻量，不读全库）。"""
    centers = np.load(centers_npy)
    if centers.ndim != 2 or centers.shape[0] < 2:
        raise ValueError(f"Unexpected centers shape: {centers.shape}")

    pca = PCA(n_components=2)
    xy = pca.fit_transform(centers.astype(np.float32, copy=False))

    fig, ax = plt.subplots(figsize=(10, 8))
    sc = ax.scatter(
        xy[:, 0],
        xy[:, 1],
        c=np.arange(len(xy)),
        cmap="turbo",
        s=12,
        alpha=0.65,
        rasterized=True,
    )
    plt.colorbar(sc, ax=ax, label="cluster id", fraction=0.046, pad=0.04)
    ax.set_title(title)
    ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]:.1%})")
    ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]:.1%})")

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved centers PCA to {output_path}")


def visualize_step1_output(
    step1_output_dir: Path,
    out_dir: Optional[Path] = None,
    centers_filename: str = "cluster_centers.npy",
):
    """将 step1_output 下的聚类结果导出为 PNG（统计图 + 中心 PCA）。"""
    out_dir = out_dir or (step1_output_dir / "viz")
    out_dir.mkdir(parents=True, exist_ok=True)
    plot_cluster_stats_summary(
        step1_output_dir,
        out_dir / "cluster_stats_summary.png",
        title=f"Clustering stats: {step1_output_dir.name}",
    )
    centers_path = step1_output_dir / centers_filename
    if centers_path.exists():
        plot_cluster_centers_pca(
            centers_path,
            out_dir / "cluster_centers_pca.png",
            title="KMeans cluster centers (PCA 2D)",
        )
    else:
        print(f"Skip centers PCA: {centers_path} not found")


def plot_cluster_comparison(
    journal_dir: Path,
    random_dir: Path,
    output_path: Path
):
    """生成对比可视化图"""
    journal_data = load_cluster_data(journal_dir)
    random_data = load_cluster_data(random_dir)

    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle("Clustering Comparison: Journal vs Random 50k", fontsize=16, fontweight='bold')

    for idx, (name, data) in enumerate([("Journal", journal_data), ("Random 50k", random_data)]):
        labels = list(data["labels_map"].values())
        stats = data["stats"]

        # 1. 簇大小分布 (柱状图)
        ax = axes[idx][0]
        cluster_sizes = Counter(labels)
        # 排除噪声点
        valid_sizes = sorted([v for k, v in cluster_sizes.items() if k >= 0], reverse=True)
        ax.bar(range(len(valid_sizes)), valid_sizes, color='steelblue', alpha=0.7)
        ax.set_title(f"{name}: Cluster Size Distribution")
        ax.set_xlabel("Cluster (sorted by size)")
        ax.set_ylabel("Number of steps")
        n_noise = cluster_sizes.get(-1, 0)
        ax.text(0.95, 0.95, f"Clusters: {len(valid_sizes)}\nNoise: {n_noise}",
                transform=ax.transAxes, ha='right', va='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

        # 2. 簇大小 CDF
        ax = axes[idx][1]
        if valid_sizes:
            sorted_sizes = sorted(valid_sizes)
            cumulative = np.cumsum(sorted_sizes) / sum(sorted_sizes)
            ax.plot(range(len(sorted_sizes)), cumulative, 'b-', linewidth=2)
            ax.set_title(f"{name}: Cumulative Distribution of Cluster Sizes")
            ax.set_xlabel("Cluster (sorted by size, ascending)")
            ax.set_ylabel("Cumulative proportion")
            ax.axhline(y=0.9, color='r', linestyle='--', alpha=0.5, label='90%')
            ax.legend()

        # 3. 质量指标
        ax = axes[idx][2]
        metrics = stats.get("metrics", {})
        metric_names = ['silhouette', 'calinski_harabasz', 'davies_bouldin']
        metric_values = [metrics.get(m, 0) for m in metric_names]
        bars = ax.barh(metric_names, metric_values, color=['green', 'blue', 'red'], alpha=0.7)
        ax.set_title(f"{name}: Clustering Quality Metrics")
        for bar, val in zip(bars, metric_values):
            ax.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height()/2,
                    f'{val:.4f}', va='center')

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved comparison plot to {output_path}")


def plot_single_cluster(output_dir: Path, lance_db_dir: Path, output_path: Path, title: str = ""):
    """对单个聚类结果生成 PCA 降维可视化（只读需要的列）"""
    from ..db import LanceVectorStore

    vector_store = LanceVectorStore(db_path=lance_db_dir, table_name="chain_embeddings")
    arrow_table = vector_store.table.to_arrow(columns=["vector", "cluster_id"])
    vectors = np.array(arrow_table.column("vector").to_pylist(), dtype=np.float32)
    cluster_ids = np.array(arrow_table.column("cluster_id").to_pylist())
    vector_store.close()

    # PCA 降维到 2D
    pca = PCA(n_components=2)
    coords_2d = pca.fit_transform(vectors)

    fig, ax = plt.subplots(figsize=(12, 8))

    # 噪声点
    noise_mask = cluster_ids == -1
    if noise_mask.any():
        ax.scatter(coords_2d[noise_mask, 0], coords_2d[noise_mask, 1],
                   c='lightgray', s=5, alpha=0.3, label='noise')

    # 各簇
    unique_labels = sorted(set(cluster_ids) - {-1})
    cmap = plt.cm.get_cmap('tab20', len(unique_labels))
    for i, cid in enumerate(unique_labels):
        mask = cluster_ids == cid
        ax.scatter(coords_2d[mask, 0], coords_2d[mask, 1],
                   c=[cmap(i)], s=8, alpha=0.5, label=f'C{cid}')

    ax.set_title(f"PCA Visualization: {title}" if title else "PCA Visualization")
    ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]:.1%})")
    ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]:.1%})")

    # 只在簇数量少时显示图例
    if len(unique_labels) <= 20:
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=8)

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved PCA plot to {output_path}")
