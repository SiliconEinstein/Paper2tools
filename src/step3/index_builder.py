"""
Step3 索引构建器 - 扫描 workflow 目录并建立检索索引
"""

import json
import yaml
from pathlib import Path
from typing import Dict, List
from datetime import datetime
from collections import defaultdict

from .utils import (
    extract_methods_from_extractions,
    infer_workflow_name,
    infer_problem_description,
    infer_io_types,
    generate_keywords,
    compute_similarity_signature,
    extract_keywords
)
from ..db import LanceVectorStore
from ..db.schema import WORKFLOW_EMBEDDING_SCHEMA


def scan_workflow_directories(workflow_dirs: List[str], verbose: bool = True) -> List[Path]:
    """
    扫描 workflow 目录，找到所有已完成的 workflow

    Args:
        workflow_dirs: workflow 目录列表
        verbose: 是否打印详细信息

    Returns:
        已完成的 workflow 目录列表
    """
    completed_workflows = []

    for dir_path in workflow_dirs:
        dir_path = Path(dir_path)
        if not dir_path.exists():
            if verbose:
                print(f"  ⚠ Directory not found: {dir_path}", flush=True)
            continue

        # 查找所有 cluster_N 目录
        for cluster_dir in sorted(dir_path.glob("cluster_*")):
            if not cluster_dir.is_dir():
                continue

            # 检查必需文件
            required_files = [
                cluster_dir / "workflow_structure.json",
                cluster_dir / "paper_extractions.yaml"
            ]

            if all(f.exists() for f in required_files):
                completed_workflows.append(cluster_dir)
                if verbose:
                    print(f"  ✓ Found: {cluster_dir}", flush=True)

    return completed_workflows


def generate_workflow_meta(workflow_dir: Path, force_regenerate: bool = False) -> Dict:
    """
    生成或读取 workflow_meta.json

    Args:
        workflow_dir: workflow 目录
        force_regenerate: 是否强制重新生成

    Returns:
        workflow_meta 字典
    """
    meta_file = workflow_dir / "workflow_meta.json"

    # 如果已存在且不强制重新生成，直接读取
    if meta_file.exists() and not force_regenerate:
        with open(meta_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    # 读取现有文件
    workflow_structure = json.load(open(workflow_dir / "workflow_structure.json", 'r', encoding='utf-8'))
    paper_extractions = yaml.safe_load(open(workflow_dir / "paper_extractions.yaml", 'r', encoding='utf-8'))

    selected_chains_file = workflow_dir / "selected_chains.json"
    if selected_chains_file.exists():
        selected_chains = json.load(open(selected_chains_file, 'r', encoding='utf-8'))
    else:
        selected_chains = {}

    # 提取信息
    cluster_id = workflow_dir.name
    domain = workflow_dir.parent.parent.name

    # 从 workflow_structure 提取
    stages_data = workflow_structure.get("stages", [])
    main_stages = []
    for stage in stages_data:
        # 兼容两种格式：{"name": "..."} 或 {"stage": "..."}
        stage_name = stage.get("name") or stage.get("stage", "")
        if stage_name:
            main_stages.append(stage_name)

    # 从 paper_extractions 提取
    key_methods = extract_methods_from_extractions(paper_extractions)
    tools = []  # 简化处理，可从 paper_extractions 提取

    # 推断 workflow_name
    workflow_name = infer_workflow_name(main_stages, key_methods)

    # 推断 problem_description
    problem_description = infer_problem_description(paper_extractions, main_stages)

    # 推断 input/output types
    input_types, output_types = infer_io_types(paper_extractions)

    # 生成 keywords
    keywords = generate_keywords(key_methods, tools, main_stages)

    # 计算 similarity_signature
    similarity_signature = compute_similarity_signature(key_methods, main_stages)

    # 统计信息
    if isinstance(paper_extractions, list):
        num_papers = len(paper_extractions)
    elif isinstance(paper_extractions, dict):
        if "papers" in paper_extractions:
            num_papers = len(paper_extractions["papers"])
        else:
            num_papers = len([k for k in paper_extractions.keys() if isinstance(paper_extractions[k], dict)])
    else:
        num_papers = 0

    # selected_chains 可能是 list 或 dict
    if isinstance(selected_chains, list):
        num_chains = len(selected_chains)
    elif isinstance(selected_chains, dict):
        num_chains = len(selected_chains.get("chains", []))
    else:
        num_chains = 0

    # 构建 workflow_meta
    workflow_meta = {
        "cluster_id": cluster_id,
        "domain": domain,
        "workflow_name": workflow_name,
        "workflow_name_en": workflow_name,  # 简化处理
        "problem_description": problem_description,
        "problem_description_en": problem_description,  # 简化处理
        "input_types": input_types,
        "output_types": output_types,
        "key_methods": key_methods,
        "main_stages": main_stages,
        "keywords": keywords,
        "keywords_en": keywords,  # 简化处理
        "similarity_signature": similarity_signature,
        "statistics": {
            "total_papers": num_papers,
            "total_chains": num_chains,
            "creation_date": datetime.now().isoformat()
        }
    }

    # 保存到文件
    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump(workflow_meta, f, ensure_ascii=False, indent=2)

    return workflow_meta


def build_vector_index(workflow_metas: List[Dict], index_dir: Path, embedder, verbose: bool = True):
    """
    构建向量索引

    Args:
        workflow_metas: workflow_meta 列表
        index_dir: 索引目录
        embedder: embedding 模型
        verbose: 是否打印详细信息
    """
    if verbose:
        print(f"\n  Building vector index...", flush=True)

    if not workflow_metas:
        if verbose:
            print(f"  ⚠ No workflows to index", flush=True)
        return

    # 准备数据
    texts = [meta["problem_description"] for meta in workflow_metas]

    # 批量 embedding（使用 async 接口）
    if verbose:
        print(f"  Embedding {len(texts)} problem descriptions...", flush=True)

    import asyncio

    async def embed_all():
        results = []
        for text in texts:
            vectors = await embedder._call_api_batch([text])
            results.append(vectors[0])
        return results

    embeddings = asyncio.run(embed_all())

    # 构建 LanceDB 数据
    records = []
    for meta, embedding in zip(workflow_metas, embeddings):
        workflow_id = f"{meta['domain']}_{meta['cluster_id']}"

        record = {
            "workflow_id": workflow_id,
            "cluster_id": meta["cluster_id"],
            "domain": meta["domain"],
            "workflow_name": meta["workflow_name"],
            "workflow_name_en": meta["workflow_name_en"],
            "problem_description": meta["problem_description"],
            "problem_description_en": meta["problem_description_en"],
            "vector": embedding,
            "keywords": meta["keywords"],
            "keywords_en": meta["keywords_en"],
            "input_types": meta["input_types"],
            "output_types": meta["output_types"],
            "key_methods": json.dumps(meta["key_methods"], ensure_ascii=False),
            "main_stages": meta["main_stages"],
            "num_papers": meta["statistics"]["total_papers"],
            "num_chains": meta["statistics"]["total_chains"],
            "avg_intra_similarity": 0.0,  # 可从 cluster_metadata 读取
            "creation_date": meta["statistics"]["creation_date"],
            "workflow_dir": str(meta.get("workflow_dir", ""))
        }

        records.append(record)

    # 写入 LanceDB
    vector_store = LanceVectorStore(
        db_path=index_dir,
        table_name="workflow_embeddings",
        schema=WORKFLOW_EMBEDDING_SCHEMA
    )

    # 直接添加到 pending writes 并 flush
    vector_store._pending_writes.extend(records)
    vector_store.flush()
    vector_store.close()

    if verbose:
        print(f"  ✓ Vector index built: {len(records)} workflows", flush=True)


def build_inverted_indexes(workflow_metas: List[Dict], index_dir: Path, verbose: bool = True):
    """
    构建倒排索引

    Args:
        workflow_metas: workflow_meta 列表
        index_dir: 索引目录
        verbose: 是否打印详细信息
    """
    if verbose:
        print(f"\n  Building inverted indexes...", flush=True)

    # 关键词倒排索引
    keyword_index = defaultdict(list)
    for meta in workflow_metas:
        workflow_id = f"{meta['domain']}_{meta['cluster_id']}"
        for keyword in meta["keywords"]:
            keyword_index[keyword].append(workflow_id)

    # 类型倒排索引
    type_index = defaultdict(list)
    for meta in workflow_metas:
        workflow_id = f"{meta['domain']}_{meta['cluster_id']}"
        for dtype in meta["input_types"] + meta["output_types"]:
            type_index[dtype].append(workflow_id)

    # 方法倒排索引
    method_index = defaultdict(list)
    for meta in workflow_metas:
        workflow_id = f"{meta['domain']}_{meta['cluster_id']}"
        for method in meta["key_methods"]:
            method_name = method["name"]
            method_index[method_name].append(workflow_id)

    # 保存到文件
    index_dir.mkdir(parents=True, exist_ok=True)

    with open(index_dir / "keyword_inverted_index.json", 'w', encoding='utf-8') as f:
        json.dump(dict(keyword_index), f, ensure_ascii=False, indent=2)

    with open(index_dir / "type_index.json", 'w', encoding='utf-8') as f:
        json.dump(dict(type_index), f, ensure_ascii=False, indent=2)

    with open(index_dir / "method_index.json", 'w', encoding='utf-8') as f:
        json.dump(dict(method_index), f, ensure_ascii=False, indent=2)

    if verbose:
        print(f"  ✓ Inverted indexes built:", flush=True)
        print(f"    - Keywords: {len(keyword_index)} entries", flush=True)
        print(f"    - Types: {len(type_index)} entries", flush=True)
        print(f"    - Methods: {len(method_index)} entries", flush=True)


def build_workflow_registry(workflow_metas: List[Dict], index_dir: Path, verbose: bool = True):
    """
    构建 workflow 注册表

    Args:
        workflow_metas: workflow_meta 列表
        index_dir: 索引目录
        verbose: 是否打印详细信息
    """
    if verbose:
        print(f"\n  Building workflow registry...", flush=True)

    registry = {}
    for meta in workflow_metas:
        workflow_id = f"{meta['domain']}_{meta['cluster_id']}"
        registry[workflow_id] = meta

    registry_file = index_dir / "workflow_registry.json"
    with open(registry_file, 'w', encoding='utf-8') as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)

    if verbose:
        print(f"  ✓ Workflow registry built: {len(registry)} workflows", flush=True)
