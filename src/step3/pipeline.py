"""
Step3 主流程 - Workflow 检索系统
"""

from pathlib import Path
from typing import Dict, List

from .index_builder import (
    scan_workflow_directories,
    generate_workflow_meta,
    build_vector_index,
    build_inverted_indexes,
    build_workflow_registry
)
from .retriever import WorkflowRetriever
from .chain_search_api import ChainSearchRequest, search_reasoning_chains
from ..step1.vectorizer import create_embedder


def build_index(config: Dict) -> Dict:
    """
    构建 workflow 检索索引

    Args:
        config: 配置字典

    Returns:
        执行结果摘要
    """
    print("\n" + "=" * 60, flush=True)
    print("Step3: Building Workflow Index", flush=True)
    print("=" * 60, flush=True)

    index_config = config["index_building"]
    workflow_dirs = index_config["workflow_dirs"]
    index_dir = Path(index_config["index_dir"])
    force_regenerate = index_config.get("force_regenerate_meta", False)

    # 1. 扫描 workflow 目录
    print("\n[1/5] Scanning workflow directories...", flush=True)
    completed_workflows = scan_workflow_directories(workflow_dirs, verbose=True)

    if not completed_workflows:
        print("\n⚠ No completed workflows found. Exiting.", flush=True)
        return {
            "total_workflows": 0,
            "index_dir": str(index_dir)
        }

    print(f"\n  ✓ Found {len(completed_workflows)} completed workflows", flush=True)

    # 2. 生成或读取 workflow_meta.json
    print("\n[2/5] Generating workflow metadata...", flush=True)
    workflow_metas = []

    for i, workflow_dir in enumerate(completed_workflows, 1):
        print(f"  [{i}/{len(completed_workflows)}] {workflow_dir.name}...", flush=True)

        try:
            meta = generate_workflow_meta(workflow_dir, force_regenerate=force_regenerate)
            meta["workflow_dir"] = str(workflow_dir)
            workflow_metas.append(meta)
        except Exception as e:
            print(f"    ✗ Failed: {e}", flush=True)

    print(f"\n  ✓ Generated {len(workflow_metas)} workflow metadata", flush=True)

    # 3. 构建向量索引
    print("\n[3/5] Building vector index...", flush=True)

    embedder_config = index_config["embedder"]
    embedder = create_embedder(embedder_config)

    build_vector_index(workflow_metas, index_dir, embedder, verbose=True)

    # 4. 构建倒排索引
    print("\n[4/5] Building inverted indexes...", flush=True)
    build_inverted_indexes(workflow_metas, index_dir, verbose=True)

    # 5. 构建 workflow 注册表
    print("\n[5/5] Building workflow registry...", flush=True)
    build_workflow_registry(workflow_metas, index_dir, verbose=True)

    # 完成
    print("\n" + "=" * 60, flush=True)
    print("Index Building Complete!", flush=True)
    print("=" * 60, flush=True)
    print(f"\nIndex statistics:")
    print(f"  Total workflows: {len(workflow_metas)}")
    print(f"  Index directory: {index_dir}")
    print(f"\nNext steps:")
    print(f"  Run search queries:")
    print(f"    python -m src.main --step 3 --action search --query \"your question\"")
    print("=" * 60 + "\n", flush=True)

    return {
        "total_workflows": len(workflow_metas),
        "index_dir": str(index_dir)
    }


def search_workflows(config: Dict, query: str, top_k: int = 5, domain: str = None) -> List[Dict]:
    """
    检索 workflows

    Args:
        config: 配置字典
        query: 查询文本
        top_k: 返回结果数量
        domain: 限定领域（可选）

    Returns:
        检索结果列表
    """
    print("\n" + "=" * 60, flush=True)
    print("Step3: Searching Workflows", flush=True)
    print("=" * 60, flush=True)

    index_dir = Path(config["index_building"]["index_dir"])

    # 检查索引是否存在
    if not index_dir.exists():
        print(f"\n✗ Index not found: {index_dir}", flush=True)
        print("  Please run: python -m src.main --step 3 --action build_index", flush=True)
        return []

    # 初始化检索器
    print("\n[1/3] Initializing retriever...", flush=True)

    embedder_config = config["index_building"]["embedder"]
    embedder = create_embedder(embedder_config)

    retrieval_config = config["retrieval"]

    retriever = WorkflowRetriever(
        index_dir=index_dir,
        embedder=embedder,
        config=retrieval_config
    )

    print("  ✓ Retriever initialized", flush=True)

    # 执行检索
    print(f"\n[2/3] Searching for: \"{query}\"", flush=True)
    if domain:
        print(f"  Domain filter: {domain}", flush=True)

    results = retriever.retrieve(query, top_k=top_k, domain=domain)

    print(f"  ✓ Found {len(results)} results", flush=True)

    # 打印结果
    print("\n[3/3] Results:", flush=True)
    print("=" * 60, flush=True)

    for i, result in enumerate(results, 1):
        meta = result["workflow_meta"]
        score = result["score"]
        match_details = result["match_details"]

        print(f"\n{i}. {meta['workflow_name']}", flush=True)
        print(f"   Score: {score:.3f}", flush=True)
        print(f"   Domain: {meta['domain']}", flush=True)
        print(f"   Cluster: {meta['cluster_id']}", flush=True)
        print(f"   Problem: {meta['problem_description']}", flush=True)
        print(f"   Stages: {' → '.join(meta['main_stages'][:3])}", flush=True)
        print(f"   Match details:", flush=True)
        for source, source_score in match_details.items():
            if source_score > 0:
                print(f"     - {source}: {source_score:.3f}", flush=True)

    print("\n" + "=" * 60 + "\n", flush=True)

    # 清理
    retriever.close()

    return results


def run_step3_pipeline(config: Dict, action: str = "build_index", **kwargs) -> Dict:
    """
    Step3 主流程入口

    Args:
        config: 配置字典
        action: 操作类型 ("build_index" / "search" / "chain_search")
        **kwargs: 其他参数（如 query, top_k, domain）

    Returns:
        执行结果
    """
    if action == "build_index":
        return build_index(config)
    elif action == "search":
        query = kwargs.get("query")
        if not query:
            raise ValueError("Query is required for search action")

        top_k = kwargs.get("top_k", 5)
        domain = kwargs.get("domain")

        results = search_workflows(config, query, top_k=top_k, domain=domain)

        return {
            "query": query,
            "total_results": len(results),
            "results": results
        }
    elif action == "chain_search":
        query = kwargs.get("query")
        if not query:
            raise ValueError("Query is required for chain_search action")

        top_k = kwargs.get("top_k", 100)
        table = kwargs.get("table", "lkm_reasoning_chain_embeddings_v2")
        allow_degraded = bool(kwargs.get("allow_degraded", True))
        domain = kwargs.get("domain")

        req = ChainSearchRequest(
            query=query,
            top_k=top_k,
            table=table,
            domain=domain,
            allow_degraded=allow_degraded,
        )
        resp = search_reasoning_chains(config, req)
        return resp.to_dict()
    else:
        raise ValueError(f"Unknown action: {action}")
