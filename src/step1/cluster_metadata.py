"""
聚类元数据管理 - 将聚类结果保存到 Lance 表
支持自动阈值进化和增量更新
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
from collections import Counter

from ..db import LanceVectorStore
from ..db.schema import CLUSTER_METADATA_SCHEMA


def build_cluster_metadata(
    domain: str,
    local_cluster_id: int,
    chain_ids: List[str],
    vectors: np.ndarray,
    metadata_list: List[Dict],
    min_pair_sim: float
) -> Dict:
    """
    构建单个聚类的元数据

    Args:
        domain: 领域名称
        local_cluster_id: 领域内的局部聚类ID
        chain_ids: 思维链ID列表
        vectors: 向量矩阵 (n, d)
        metadata_list: 元数据列表（每条链的metadata）
        min_pair_sim: 创建时使用的阈值

    Returns:
        聚类元数据字典
    """
    # 提取路径和paper_id
    chain_xml_paths = [m["xml_path"] for m in metadata_list]
    paper_ids = list(set(m["paper_id"] for m in metadata_list))
    paper_md_paths = list(set(m["md_path"] for m in metadata_list))

    # 计算质心
    centroid = vectors.mean(axis=0).astype(np.float32)

    # 计算簇内相似度
    if len(vectors) > 1:
        normalized = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
        sim_matrix = normalized @ normalized.T
        # 只取上三角（不含对角线）
        triu_indices = np.triu_indices(len(vectors), k=1)
        similarities = sim_matrix[triu_indices]
        avg_sim = float(similarities.mean())
        min_sim = float(similarities.min())
    else:
        avg_sim = 1.0
        min_sim = 1.0

    return {
        "global_cluster_id": f"{domain}_{local_cluster_id}",
        "domain": domain,
        "local_cluster_id": local_cluster_id,
        "num_chains": len(chain_ids),
        "num_papers": len(paper_ids),
        "chain_xml_paths": chain_xml_paths,
        "paper_ids": paper_ids,
        "paper_md_paths": paper_md_paths,
        "centroid": centroid.tolist(),
        "avg_intra_similarity": avg_sim,
        "min_intra_similarity": min_sim,
        "min_pair_sim_threshold": min_pair_sim,
        "created_at": datetime.now(),
        "last_updated": datetime.now(),
    }


def cluster_and_save_to_lance(
    vector_store: LanceVectorStore,
    cluster_store: LanceVectorStore,
    domain: str,
    min_pair_sim: float = 0.6,
    max_size: int = 300,
    auto_evolve: bool = True,
    evolve_threshold: float = 0.6,
    evolve_step: float = 0.02,
    verbose: bool = True
) -> Tuple[np.ndarray, int]:
    """
    执行聚类并保存到 Lance 表，支持自动阈值进化

    Args:
        vector_store: 向量存储（chain_embeddings表）
        cluster_store: 聚类元数据存储（cluster_metadata表）
        domain: 领域名称
        min_pair_sim: 最小簇间相似度阈值
        max_size: 每个簇最大思维链数
        auto_evolve: 是否自动进化阈值
        evolve_threshold: 触发进化的大簇比例（如0.6表示60%的簇超过max_size）
        evolve_step: 每次进化的阈值增量
        verbose: 是否打印详细信息

    Returns:
        (labels, n_clusters): 聚类标签和簇数量
    """
    from .cluster.agglomerative import AgglomerativeConstrainedClustering

    if verbose:
        print(f"\n{'='*60}")
        print(f"Clustering with agglomerative (min_pair_sim={min_pair_sim:.2f})")
        print(f"{'='*60}")

    # 1. 从 vector_store 读取该领域的所有向量
    if verbose:
        print(f"Loading vectors for domain '{domain}'...")

    # 使用 where 过滤获取该领域的数据
    filter_expr = f"domain = '{domain}'"
    arrow_table = vector_store.table.search().where(filter_expr).limit(999999999).to_arrow()

    chain_ids = arrow_table.column("chain_id").to_pylist()
    vectors = np.array(arrow_table.column("vector").to_pylist(), dtype=np.float32)

    # 提取元数据
    metadata_list = []
    for i in range(len(chain_ids)):
        metadata_list.append({
            "paper_id": arrow_table.column("paper_id")[i].as_py(),
            "xml_path": arrow_table.column("xml_path")[i].as_py(),
            "md_path": arrow_table.column("md_path")[i].as_py(),
        })

    if verbose:
        print(f"  Loaded {len(chain_ids)} chains from domain '{domain}'")

    # 2. 执行 agglomerative 聚类
    if verbose:
        print(f"Running agglomerative clustering...")

    config = {
        "max_size": max_size,
        "min_pair_sim": min_pair_sim,
        "micro_k": 5000,  # 两阶段聚类的微簇数量
    }

    algorithm = AgglomerativeConstrainedClustering(config, random_seed=42)
    labels = algorithm.fit(vectors)
    n_clusters = algorithm.n_clusters

    if verbose:
        print(f"  Generated {n_clusters} clusters")

    # 3. 检查是否需要自动进化阈值
    if auto_evolve:
        cluster_sizes = Counter(labels)
        large_clusters = sum(1 for size in cluster_sizes.values() if size > max_size)
        large_ratio = large_clusters / n_clusters if n_clusters > 0 else 0

        if verbose:
            print(f"  Large clusters (>{max_size}): {large_clusters}/{n_clusters} ({large_ratio:.1%})")

        if large_ratio > evolve_threshold:
            new_threshold = min_pair_sim + evolve_step
            if verbose:
                print(f"  ⚠ Auto-evolving threshold: {min_pair_sim:.2f} → {new_threshold:.2f}")

            # 递归调用，使用新阈值
            return cluster_and_save_to_lance(
                vector_store=vector_store,
                cluster_store=cluster_store,
                domain=domain,
                min_pair_sim=new_threshold,
                max_size=max_size,
                auto_evolve=auto_evolve,
                evolve_threshold=evolve_threshold,
                evolve_step=evolve_step,
                verbose=verbose
            )

    # 4. 构建聚类元数据并保存到 cluster_store
    if verbose:
        print(f"Saving cluster metadata to Lance...")

    cluster_records = []
    for cluster_id in range(n_clusters):
        mask = (labels == cluster_id)
        cluster_chain_ids = [chain_ids[i] for i in np.where(mask)[0]]
        cluster_vectors = vectors[mask]
        cluster_metadata = [metadata_list[i] for i in np.where(mask)[0]]

        metadata_record = build_cluster_metadata(
            domain=domain,
            local_cluster_id=cluster_id,
            chain_ids=cluster_chain_ids,
            vectors=cluster_vectors,
            metadata_list=cluster_metadata,
            min_pair_sim=min_pair_sim
        )
        cluster_records.append(metadata_record)

    # 批量写入
    if cluster_records:
        cluster_store.table.add(cluster_records)
        if verbose:
            print(f"  Saved {len(cluster_records)} cluster metadata records")

    # 5. 更新 vector_store 中的 cluster_id 字段
    if verbose:
        print(f"Updating cluster_id in vector store...")

    # LanceDB 不支持直接 UPDATE，需要重新写入
    # 这里我们采用简单策略：读取所有记录，更新 cluster_id，然后重新写入
    # 注意：这对大数据集可能较慢，生产环境应该使用增量更新策略

    # 读取该领域的所有记录
    all_records = arrow_table.to_pylist()

    # 更新 cluster_id
    chain_id_to_label = dict(zip(chain_ids, labels))
    for record in all_records:
        cid = record["chain_id"]
        if cid in chain_id_to_label:
            record["cluster_id"] = int(chain_id_to_label[cid])

    # 删除旧记录并写入新记录
    # 注意：LanceDB 的删除操作需要使用 delete() 方法
    vector_store.table.delete(filter_expr)
    vector_store.table.add(all_records)

    if verbose:
        print(f"  Updated cluster_id for {len(all_records)} chains")
        print(f"{'='*60}")
        print(f"Clustering complete!")
        print(f"  Final threshold: {min_pair_sim:.2f}")
        print(f"  Total clusters: {n_clusters}")
        print(f"  Avg cluster size: {len(chain_ids) / n_clusters:.1f}")
        print(f"{'='*60}\n")

    return labels, n_clusters


def incremental_clustering(
    vector_store: LanceVectorStore,
    cluster_store: LanceVectorStore,
    domain: str,
    new_chain_ids: List[str],
    verbose: bool = True
) -> None:
    """
    增量添加新思维链到现有聚类

    策略：
    1. 对每条新思维链，找到最相似的现有聚类质心
    2. 如果相似度 >= min_pair_sim，加入该聚类
    3. 否则，创建新聚类

    Args:
        vector_store: 向量存储
        cluster_store: 聚类元数据存储
        domain: 领域名称
        new_chain_ids: 新增的思维链ID列表
        verbose: 是否打印详细信息
    """
    if verbose:
        print(f"\n{'='*60}")
        print(f"Incremental clustering for {len(new_chain_ids)} new chains")
        print(f"{'='*60}")

    # 1. 获取新思维链的向量和元数据
    new_chains = vector_store.get_by_ids(new_chain_ids)
    new_vectors = np.array([c["vector"] for c in new_chains], dtype=np.float32)
    new_metadata = [c["metadata"] for c in new_chains]

    # 2. 获取现有聚类的质心和阈值
    filter_expr = f"domain = '{domain}'"
    existing_clusters = cluster_store.table.search().where(filter_expr).limit(999999999).to_pylist()

    if not existing_clusters:
        if verbose:
            print("  No existing clusters found, creating new clusters for all chains")
        # 如果没有现有聚类，为所有新链创建新聚类
        for i, (chain_id, vector, metadata) in enumerate(zip(new_chain_ids, new_vectors, new_metadata)):
            cluster_metadata = build_cluster_metadata(
                domain=domain,
                local_cluster_id=i,
                chain_ids=[chain_id],
                vectors=vector.reshape(1, -1),
                metadata_list=[metadata],
                min_pair_sim=0.6
            )
            cluster_store.table.add([cluster_metadata])
        return

    centroids = np.array([c["centroid"] for c in existing_clusters], dtype=np.float32)
    thresholds = [c["min_pair_sim_threshold"] for c in existing_clusters]
    global_cluster_ids = [c["global_cluster_id"] for c in existing_clusters]

    if verbose:
        print(f"  Found {len(existing_clusters)} existing clusters")

    # 3. 为每条新链分配聚类
    assignments = []  # (chain_id, cluster_idx, similarity)
    new_clusters = []  # 需要创建的新聚类

    for chain_id, vector, metadata in zip(new_chain_ids, new_vectors, new_metadata):
        # 计算与所有质心的余弦相似度
        vector_norm = vector / np.linalg.norm(vector)
        centroids_norm = centroids / np.linalg.norm(centroids, axis=1, keepdims=True)
        similarities = centroids_norm @ vector_norm

        best_idx = int(np.argmax(similarities))
        best_sim = float(similarities[best_idx])

        if best_sim >= thresholds[best_idx]:
            # 加入现有聚类
            assignments.append((chain_id, best_idx, best_sim))
        else:
            # 创建新聚类
            new_cluster_id = len(existing_clusters) + len(new_clusters)
            cluster_metadata = build_cluster_metadata(
                domain=domain,
                local_cluster_id=new_cluster_id,
                chain_ids=[chain_id],
                vectors=vector.reshape(1, -1),
                metadata_list=[metadata],
                min_pair_sim=thresholds[0] if thresholds else 0.6
            )
            new_clusters.append(cluster_metadata)

    if verbose:
        print(f"  Assigned {len(assignments)} chains to existing clusters")
        print(f"  Created {len(new_clusters)} new clusters")

    # 4. 更新现有聚类的元数据
    if assignments:
        if verbose:
            print(f"  Updating metadata for {len(set(a[1] for a in assignments))} affected clusters...")

        # 按簇分组
        cluster_updates = {}
        for chain_id, cluster_idx, _ in assignments:
            if cluster_idx not in cluster_updates:
                cluster_updates[cluster_idx] = []
            cluster_updates[cluster_idx].append(chain_id)

        # 为每个受影响的簇重新计算元数据
        updated_records = []
        for cluster_idx, added_chain_ids in cluster_updates.items():
            old_cluster = existing_clusters[cluster_idx]

            # 获取旧簇的所有链ID
            old_chain_ids = [
                path.split('/')[-1].replace('.xml', '')
                for path in old_cluster["chain_xml_paths"]
            ]

            # 合并新旧链ID
            all_chain_ids = old_chain_ids + added_chain_ids

            # 获取所有向量和元数据
            all_chains = vector_store.get_by_ids(all_chain_ids)
            all_vectors = np.array([c["vector"] for c in all_chains], dtype=np.float32)
            all_metadata = [c["metadata"] for c in all_chains]

            # 重新构建元数据
            updated_metadata = build_cluster_metadata(
                domain=domain,
                local_cluster_id=old_cluster["local_cluster_id"],
                chain_ids=all_chain_ids,
                vectors=all_vectors,
                metadata_list=all_metadata,
                min_pair_sim=old_cluster["min_pair_sim_threshold"]
            )
            updated_records.append(updated_metadata)

        # 删除旧记录并添加新记录
        if updated_records:
            global_ids_to_delete = [existing_clusters[idx]["global_cluster_id"]
                                   for idx in cluster_updates.keys()]
            for gid in global_ids_to_delete:
                cluster_store.table.delete(f"global_cluster_id = '{gid}'")
            cluster_store.table.add(updated_records)

            if verbose:
                print(f"  ✓ Updated {len(updated_records)} cluster metadata records")

    # 5. 保存新聚类
    if new_clusters:
        cluster_store.table.add(new_clusters)
        if verbose:
            print(f"  ✓ Added {len(new_clusters)} new cluster metadata records")

    # 6. 更新 vector_store 中的 cluster_id
    if assignments or new_clusters:
        if verbose:
            print(f"  Updating cluster_id in vector store...")

        # 构建 chain_id -> cluster_id 映射
        chain_to_cluster = {}

        # 已分配到现有簇的链
        for chain_id, cluster_idx, _ in assignments:
            local_cluster_id = existing_clusters[cluster_idx]["local_cluster_id"]
            chain_to_cluster[chain_id] = local_cluster_id

        # 新创建的簇
        for cluster_meta in new_clusters:
            local_cluster_id = cluster_meta["local_cluster_id"]
            for path in cluster_meta["chain_xml_paths"]:
                chain_id = path.split('/')[-1].replace('.xml', '')
                chain_to_cluster[chain_id] = local_cluster_id

        # 批量更新
        for chain_id, cluster_id in chain_to_cluster.items():
            vector_store.batch_update_metadata(
                [chain_id],
                [{"cluster_id": cluster_id}]
            )

        if verbose:
            print(f"  ✓ Updated cluster_id for {len(chain_to_cluster)} chains")

    if verbose:
        print(f"{'='*60}\n")
