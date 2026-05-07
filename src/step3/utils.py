"""
Step3 辅助函数
"""

import re
import json
import hashlib
from typing import List, Dict, Set
from collections import Counter


def extract_keywords(text: str, stopwords: Set[str] = None, min_length: int = 2) -> List[str]:
    """
    从文本中提取关键词

    Args:
        text: 输入文本
        stopwords: 停用词集合
        min_length: 最小关键词长度

    Returns:
        关键词列表
    """
    if stopwords is None:
        stopwords = set()

    # 中文分词（简单实现：按标点和空格分割）
    # 保留中文、英文、数字
    tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+|[0-9]+', text.lower())

    # 过滤停用词和短词
    keywords = [
        token for token in tokens
        if len(token) >= min_length and token not in stopwords
    ]

    return keywords


def detect_data_types(text: str, patterns: List[Dict] = None) -> List[str]:
    """
    从文本中识别数据类型

    Args:
        text: 输入文本
        patterns: 类型识别规则列表 [{"pattern": "...", "type": "..."}, ...]

    Returns:
        识别到的数据类型列表
    """
    if patterns is None:
        patterns = []

    detected_types = []

    for rule in patterns:
        pattern = rule["pattern"]
        dtype = rule["type"]

        if re.search(pattern, text, re.IGNORECASE):
            detected_types.append(dtype)

    return list(set(detected_types))


def detect_methods(text: str, patterns: List[Dict] = None) -> List[str]:
    """
    从文本中识别方法名

    Args:
        text: 输入文本
        patterns: 方法识别规则列表 [{"pattern": "...", "method": "..."}, ...]

    Returns:
        识别到的方法名列表
    """
    if patterns is None:
        patterns = []

    detected_methods = []

    for rule in patterns:
        pattern = rule["pattern"]
        method = rule["method"]

        if re.search(pattern, text, re.IGNORECASE):
            detected_methods.append(method)

    return list(set(detected_methods))


def extract_methods_from_extractions(paper_extractions) -> List[Dict]:
    """
    从 paper_extractions.yaml 中提取关键方法

    Args:
        paper_extractions: paper_extractions.yaml 的内容（list 或 dict）

    Returns:
        关键方法列表 [{"name": "...", "name_en": "...", "frequency": 0.8}, ...]
    """
    method_counter = Counter()

    # 处理 list 格式（新格式）
    if isinstance(paper_extractions, list):
        papers = paper_extractions
    # 处理 dict 格式（旧格式）
    elif isinstance(paper_extractions, dict):
        if "papers" in paper_extractions:
            papers = paper_extractions["papers"]
        else:
            papers = list(paper_extractions.values())
    else:
        return []

    # 从每篇论文提取方法
    for paper_data in papers:
        if not isinstance(paper_data, dict):
            continue

        # 从 algorithm_layer 提取 method_family
        algo_layer = paper_data.get("algorithm_layer", {})
        if isinstance(algo_layer, dict):
            method_family = algo_layer.get("method_family", "")
            if method_family:
                method_counter[method_family] += 1

        # 从 tools 提取
        tools = paper_data.get("tools", [])
        if isinstance(tools, list):
            for tool in tools:
                if isinstance(tool, str):
                    method_counter[tool] += 1

    # 计算频率
    total_papers = len(papers)
    if total_papers == 0:
        return []

    key_methods = []
    for method, count in method_counter.most_common(10):
        key_methods.append({
            "name": method,
            "name_en": method,
            "frequency": count / total_papers
        })

    return key_methods


def infer_workflow_name(main_stages: List[str], key_methods: List[Dict]) -> str:
    """
    从主要阶段和关键方法推断 workflow 名称

    Args:
        main_stages: 主要阶段列表
        key_methods: 关键方法列表

    Returns:
        workflow 名称
    """
    # 简化实现：取前3个阶段拼接
    if len(main_stages) >= 3:
        return " → ".join(main_stages[:3])
    elif main_stages:
        return " → ".join(main_stages)
    elif key_methods:
        return " + ".join([m["name"] for m in key_methods[:3]])
    else:
        return "未命名工作流"


def infer_problem_description(paper_extractions, main_stages: List[str]) -> str:
    """
    从论文提取和阶段推断问题描述

    Args:
        paper_extractions: paper_extractions.yaml 的内容（list 或 dict）
        main_stages: 主要阶段列表

    Returns:
        问题描述
    """
    # 处理 list 格式
    if isinstance(paper_extractions, list):
        papers = paper_extractions
    elif isinstance(paper_extractions, dict):
        if "papers" in paper_extractions:
            papers = paper_extractions["papers"]
        else:
            papers = list(paper_extractions.values())
    else:
        papers = []

    # 从第一篇论文提取 title
    first_paper = None
    for paper_data in papers:
        if isinstance(paper_data, dict):
            first_paper = paper_data
            break

    if first_paper and "title" in first_paper:
        title = first_paper["title"]
        if main_stages:
            return f"如何通过 {' → '.join(main_stages[:2])} 解决相关问题"
        else:
            return f"关于 {title[:50]} 的研究方法"
    elif main_stages:
        return f"如何完成 {' → '.join(main_stages)}"
    else:
        return "未知研究问题"


def infer_io_types(paper_extractions) -> tuple:
    """
    从论文提取推断输入输出类型

    Args:
        paper_extractions: paper_extractions.yaml 的内容（list 或 dict）

    Returns:
        (input_types, output_types)
    """
    input_types = set()
    output_types = set()

    # 处理 list 格式
    if isinstance(paper_extractions, list):
        papers = paper_extractions
    elif isinstance(paper_extractions, dict):
        if "papers" in paper_extractions:
            papers = paper_extractions["papers"]
        else:
            papers = list(paper_extractions.values())
    else:
        papers = []

    for paper_data in papers:
        if not isinstance(paper_data, dict):
            continue

        # 从 implementation_layer 提取
        impl_layer = paper_data.get("implementation_layer", {})
        if isinstance(impl_layer, dict):
            # 输入 QC
            input_qc = impl_layer.get("input_qc", "")
            if input_qc:
                input_types.add("experimental_data")

        # 从 quantitative_results 提取
        quant_results = paper_data.get("quantitative_results", [])
        if isinstance(quant_results, list):
            for result in quant_results:
                if isinstance(result, str):
                    output_types.add("measurement_data")
                    break

    return list(input_types)[:5], list(output_types)[:5]


def generate_keywords(key_methods: List[Dict], tools: List[str], main_stages: List[str]) -> List[str]:
    """
    生成关键词列表

    Args:
        key_methods: 关键方法列表
        tools: 工具列表
        main_stages: 主要阶段列表

    Returns:
        关键词列表
    """
    keywords = set()

    # 从方法提取
    for method in key_methods:
        keywords.add(method["name"])

    # 从工具提取
    for tool in tools:
        keywords.add(tool)

    # 从阶段提取
    for stage in main_stages:
        # 分词
        tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', stage)
        keywords.update(tokens)

    return list(keywords)[:20]


def compute_similarity_signature(key_methods: List[Dict], main_stages: List[str]) -> Dict:
    """
    计算相似度签名

    Args:
        key_methods: 关键方法列表
        main_stages: 主要阶段列表

    Returns:
        相似度签名字典
    """
    method_vector = [m["frequency"] for m in key_methods[:10]]

    # 补齐到10维
    while len(method_vector) < 10:
        method_vector.append(0.0)

    stage_sequence = "_".join(main_stages)
    stage_sequence_hash = hashlib.sha256(stage_sequence.encode()).hexdigest()[:16]

    return {
        "method_vector": method_vector,
        "stage_count": len(main_stages),
        "stage_sequence_hash": stage_sequence_hash
    }
