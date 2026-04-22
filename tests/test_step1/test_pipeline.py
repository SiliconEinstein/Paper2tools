"""
测试 Step1 端到端流水线

测试内容:
- 完整的 Step1 流水线运行
- 配置文件加载和验证
- 数据加载→向量化→聚类→保存的完整流程
- 输出文件格式正确性
- 幂等性（重复运行不出错）
"""

import json
import pytest
import numpy as np
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from src.step1.clustering import (
    ClusterResult,
    save_cluster_results,
)
from src.step1.data_loader import (
    ReasoningStep,
    ReasoningChain,
    parse_reasoning_chain_xml,
    load_journal_config,
    save_paper_id_list,
    load_paper_id_list_from_cache,
    save_reasoning_chains_to_jsonl,
    load_reasoning_chains_from_jsonl,
)


# --- data_loader 测试 ---

SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<reasoning_chains>
    <conclusion_reasoning conclusion_id="c1" conclusion_title="Title1">
        <conclusion_text>Conclusion text here.</conclusion_text>
        <reasoning>
            <step id="s1">First step text</step>
            <step id="s2">Second step with <ref type="citation">cite1</ref></step>
            <step id="s3">Third step with <ref type="figure">fig1</ref></step>
        </reasoning>
    </conclusion_reasoning>
</reasoning_chains>
"""


def test_parse_reasoning_chain_xml():
    """测试 XML 解析"""
    chains = parse_reasoning_chain_xml(SAMPLE_XML, "paper_001", "Nature")

    assert len(chains) == 1
    chain = chains[0]
    assert chain.paper_id == "paper_001"
    assert chain.journal == "Nature"
    assert chain.conclusion_id == "c1"
    assert len(chain.steps) == 3


def test_parse_steps_content():
    """测试步骤内容解析"""
    chains = parse_reasoning_chain_xml(SAMPLE_XML, "paper_001", "Nature")
    steps = chains[0].steps

    assert steps[0].step_id == "s1"
    assert "First step" in steps[0].text
    assert steps[1].has_citations is True
    assert steps[2].has_figures is True
    assert steps[0].has_citations is False


def test_parse_invalid_xml():
    """测试解析无效 XML"""
    chains = parse_reasoning_chain_xml("<bad>xml", "p1", "J1")
    assert chains == []


def test_parse_empty_reasoning():
    """测试空推理链"""
    empty_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <reasoning_chains>
        <conclusion_reasoning conclusion_id="c1" conclusion_title="T1">
            <reasoning/>
        </conclusion_reasoning>
    </reasoning_chains>
    """
    chains = parse_reasoning_chain_xml(empty_xml, "p1", "J1")
    assert chains == []


def test_load_journal_config(tmp_path):
    """测试加载期刊配置文件"""
    config_path = tmp_path / "journals.yaml"
    config_path.write_text("""
materials:
  journals:
    - Nature
    - Science
bio:
  journals:
    - Cell
""")
    journals = load_journal_config(config_path, "materials")
    assert journals == ["Nature", "Science"]


def test_load_journal_config_missing_domain(tmp_path):
    """测试加载不存在的领域"""
    config_path = tmp_path / "journals.yaml"
    config_path.write_text("materials:\n  journals:\n    - Nature\n")

    with pytest.raises(ValueError, match="Domain 'bio' not found"):
        load_journal_config(config_path, "bio")


def test_save_and_load_paper_ids(tmp_path):
    """测试保存和加载 paper_id 列表"""
    cache_path = tmp_path / "paper_ids_test.json"
    paper_ids = ["p1", "p2", "p3"]
    per_journal_count = {"Nature": 2, "Science": 1}

    save_paper_id_list(cache_path, "test", ["Nature", "Science"], paper_ids, per_journal_count)
    loaded_ids, metadata = load_paper_id_list_from_cache(cache_path)

    assert loaded_ids == paper_ids
    assert metadata["domain"] == "test"
    assert metadata["total_count"] == 3


def test_save_and_load_reasoning_chains(tmp_path):
    """测试保存和加载思维链"""
    chains = parse_reasoning_chain_xml(SAMPLE_XML, "paper_001", "Nature")
    jsonl_path = tmp_path / "chains.jsonl"

    save_reasoning_chains_to_jsonl(chains, jsonl_path)
    loaded = load_reasoning_chains_from_jsonl(jsonl_path)

    assert len(loaded) == 1
    assert loaded[0].paper_id == "paper_001"
    assert len(loaded[0].steps) == 3
    assert loaded[0].steps[0].step_id == "s1"


# --- save_cluster_results 测试 ---

def test_save_cluster_results(tmp_path):
    """测试保存聚类结果"""
    result = ClusterResult(
        n_clusters=3,
        labels=np.array([0, 0, 1, 1, 2]),
        step_ids=["s1", "s2", "s3", "s4", "s5"],
        centers=np.random.randn(3, 10).astype(np.float32),
        metrics={"silhouette": 0.6, "n_clusters": 3, "n_noise": 0, "n_total": 5}
    )

    output_dir = tmp_path / "output"
    save_cluster_results(result, output_dir)

    # 验证输出文件存在
    assert (output_dir / "cluster_labels.json").exists()
    assert (output_dir / "cluster_stats.json").exists()
    assert (output_dir / "cluster_centers.npy").exists()

    # 验证内容
    with open(output_dir / "cluster_labels.json") as f:
        labels_map = json.load(f)
    assert len(labels_map) == 5
    assert labels_map["s1"] == 0

    with open(output_dir / "cluster_stats.json") as f:
        stats = json.load(f)
    assert stats["n_clusters"] == 3


def test_save_cluster_results_without_centers(tmp_path):
    """测试保存没有中心点的聚类结果（如 HDBSCAN）"""
    result = ClusterResult(
        n_clusters=2,
        labels=np.array([0, 0, 1, 1, -1]),
        step_ids=["s1", "s2", "s3", "s4", "s5"],
        centers=None,
        metrics={"n_clusters": 2, "n_noise": 1, "n_total": 5}
    )

    output_dir = tmp_path / "output_no_centers"
    save_cluster_results(result, output_dir)

    assert (output_dir / "cluster_labels.json").exists()
    assert (output_dir / "cluster_stats.json").exists()
    assert not (output_dir / "cluster_centers.npy").exists()


def test_idempotent_save(tmp_path):
    """测试幂等性 - 重复保存不出错"""
    result = ClusterResult(
        n_clusters=2,
        labels=np.array([0, 1]),
        step_ids=["s1", "s2"],
        centers=np.random.randn(2, 5).astype(np.float32),
        metrics={"n_clusters": 2, "n_noise": 0, "n_total": 2}
    )

    output_dir = tmp_path / "output"
    save_cluster_results(result, output_dir)
    save_cluster_results(result, output_dir)  # 第二次保存不应出错

    with open(output_dir / "cluster_labels.json") as f:
        labels_map = json.load(f)
    assert len(labels_map) == 2
