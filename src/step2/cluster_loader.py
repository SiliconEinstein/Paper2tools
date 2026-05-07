"""
聚类数据加载模块 - 从 Lance 表读取聚类和思维链数据
"""

from typing import List, Dict, Optional
import numpy as np

from ..db import LanceVectorStore


def load_cluster_metadata(
    cluster_store: LanceVectorStore,
    domain: str,
    cluster_ids: Optional[List[int]] = None,
    min_chains: Optional[int] = None,
    max_chains: Optional[int] = None,
    min_intra_similarity: Optional[float] = None
) -> List[Dict]:
    """
    加载指定 domain 的聚类元数据

    Args:
        cluster_store: 聚类元数据存储
        domain: 领域名称
        cluster_ids: 可选，只加载指定的聚类 ID
        min_chains: 可选，最小链数过滤
        max_chains: 可选，最大链数过滤
        min_intra_similarity: 可选，最小簇内相似度过滤

    Returns:
        聚类元数据列表
    """
    # 构建过滤条件
    filter_expr = f"domain = '{domain}'"

    # 查询所有聚类
    arrow_table = cluster_store.table.search().where(filter_expr).limit(999999999).to_arrow()
    clusters = arrow_table.to_pylist()

    # 应用过滤条件
    filtered = []
    for cluster in clusters:
        # 按 cluster_ids 过滤
        if cluster_ids is not None:
            if cluster["local_cluster_id"] not in cluster_ids:
                continue

        # 按链数过滤
        if min_chains is not None and cluster["num_chains"] < min_chains:
            continue
        if max_chains is not None and cluster["num_chains"] > max_chains:
            continue

        # 按簇内相似度过滤
        if min_intra_similarity is not None:
            if cluster["avg_intra_similarity"] < min_intra_similarity:
                continue

        filtered.append(cluster)

    # 按 local_cluster_id 排序
    filtered.sort(key=lambda x: x["local_cluster_id"])

    return filtered


def load_cluster_chains(
    vector_store: LanceVectorStore,
    domain: str,
    cluster_id: int
) -> List[Dict]:
    """
    加载指定聚类的所有思维链

    Args:
        vector_store: 向量存储
        domain: 领域名称
        cluster_id: 聚类 ID（local_cluster_id）

    Returns:
        思维链列表，每条链包含完整元数据
    """
    # 构建过滤条件
    filter_expr = f"domain = '{domain}' AND cluster_id = {cluster_id}"

    # 查询该聚类的所有链
    arrow_table = vector_store.table.search().where(filter_expr).limit(999999999).to_arrow()

    # 转换为字典列表（不包含 vector 字段以节省内存）
    chains = []
    for i in range(len(arrow_table)):
        chain = {
            "chain_id": arrow_table.column("chain_id")[i].as_py(),
            "paper_id": arrow_table.column("paper_id")[i].as_py(),
            "journal": arrow_table.column("journal")[i].as_py(),
            "domain": arrow_table.column("domain")[i].as_py(),
            "conclusion_id": arrow_table.column("conclusion_id")[i].as_py(),
            "conclusion_title": arrow_table.column("conclusion_title")[i].as_py(),
            "xml_path": arrow_table.column("xml_path")[i].as_py(),
            "md_path": arrow_table.column("md_path")[i].as_py(),
            "chain_text": arrow_table.column("chain_text")[i].as_py(),
            "cluster_id": arrow_table.column("cluster_id")[i].as_py(),
            "num_steps": arrow_table.column("num_steps")[i].as_py(),
            "has_citations": arrow_table.column("has_citations")[i].as_py(),
            "has_figures": arrow_table.column("has_figures")[i].as_py(),
        }
        chains.append(chain)

    return chains
