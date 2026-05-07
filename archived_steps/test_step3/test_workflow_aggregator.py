"""
测试工作流聚合模块

测试内容:
- workflow 相似度计算
- 相似 workflow 的聚合
- workflow 描述生成
- 频率统计
- 边界情况（完全相同、完全不同）

注：workflow_aggregator.py 目前为占位文件（仅含 TODO），
下面测试的是数据结构约定和将来的接口契约。
"""

import pytest
from collections import Counter
from src.step3.schema import Workflow, WorkflowStep


# ---- 辅助函数 ----

def _make_workflow(wid: str, tool_chain: list[str]) -> Workflow:
    """快速构建测试用 Workflow"""
    steps = [
        WorkflowStep(step_id=i + 1, logic_description=f"Step {i+1}", tool_intent="",
                      suggested_tools=[tool])
        for i, tool in enumerate(tool_chain)
    ]
    return Workflow(
        workflow_id=wid,
        title=f"Workflow {wid}",
        description="test",
        source_ids=[wid],
        steps=steps
    )


def _get_tool_signature(workflow: Workflow) -> tuple:
    """提取 workflow 的工具链签名"""
    return tuple(
        tuple(s.suggested_tools) for s in workflow.steps
    )


# ---- 工具链签名测试 ----

def test_tool_signature_identical():
    """测试相同工具链的签名一致"""
    w1 = _make_workflow("w1", ["VASP", "LAMMPS", "Python"])
    w2 = _make_workflow("w2", ["VASP", "LAMMPS", "Python"])

    assert _get_tool_signature(w1) == _get_tool_signature(w2)


def test_tool_signature_different():
    """测试不同工具链的签名不同"""
    w1 = _make_workflow("w1", ["VASP", "LAMMPS"])
    w2 = _make_workflow("w2", ["LAMMPS", "VASP"])  # 顺序不同

    assert _get_tool_signature(w1) != _get_tool_signature(w2)


def test_tool_signature_subset():
    """测试子集工具链的签名不同"""
    w1 = _make_workflow("w1", ["VASP", "LAMMPS", "Python"])
    w2 = _make_workflow("w2", ["VASP", "LAMMPS"])

    assert _get_tool_signature(w1) != _get_tool_signature(w2)


# ---- 相似度计算测试 ----

def _jaccard_similarity(set1: set, set2: set) -> float:
    """计算 Jaccard 相似度"""
    if not set1 and not set2:
        return 1.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


def test_similarity_identical_workflows():
    """测试完全相同的 workflow 相似度为 1"""
    tools1 = {"VASP", "LAMMPS", "Python"}
    tools2 = {"VASP", "LAMMPS", "Python"}

    sim = _jaccard_similarity(tools1, tools2)
    assert sim == 1.0


def test_similarity_completely_different():
    """测试完全不同的 workflow 相似度为 0"""
    tools1 = {"VASP", "LAMMPS"}
    tools2 = {"Python", "R"}

    sim = _jaccard_similarity(tools1, tools2)
    assert sim == 0.0


def test_similarity_partial_overlap():
    """测试部分重叠的 workflow 相似度"""
    tools1 = {"VASP", "LAMMPS", "Python"}
    tools2 = {"VASP", "Python", "R"}

    sim = _jaccard_similarity(tools1, tools2)
    # intersection = {VASP, Python} = 2, union = {VASP, LAMMPS, Python, R} = 4
    assert sim == pytest.approx(0.5)


def test_similarity_empty_sets():
    """测试空集合的相似度"""
    assert _jaccard_similarity(set(), set()) == 1.0
    assert _jaccard_similarity({"A"}, set()) == 0.0


# ---- 聚合逻辑测试 ----

def test_group_by_signature():
    """测试按工具链签名分组"""
    workflows = [
        _make_workflow("w1", ["VASP", "LAMMPS"]),
        _make_workflow("w2", ["VASP", "LAMMPS"]),
        _make_workflow("w3", ["Python", "R"]),
    ]

    groups = {}
    for w in workflows:
        sig = _get_tool_signature(w)
        groups.setdefault(sig, []).append(w)

    assert len(groups) == 2
    sigs = list(groups.keys())
    assert len(groups[sigs[0]]) + len(groups[sigs[1]]) == 3


def test_frequency_counting():
    """测试 workflow 频率统计"""
    workflows = [
        _make_workflow("w1", ["VASP", "LAMMPS"]),
        _make_workflow("w2", ["VASP", "LAMMPS"]),
        _make_workflow("w3", ["VASP", "LAMMPS"]),
        _make_workflow("w4", ["Python"]),
    ]

    sig_counts = Counter(_get_tool_signature(w) for w in workflows)
    most_common = sig_counts.most_common(1)

    assert most_common[0][1] == 3


def test_merge_source_ids():
    """测试合并 source_ids"""
    w1 = _make_workflow("w1", ["VASP"])
    w2 = _make_workflow("w2", ["VASP"])

    merged_sources = list(set(w1.source_ids + w2.source_ids))
    assert len(merged_sources) == 2
    assert "w1" in merged_sources
    assert "w2" in merged_sources


# ---- 边界情况 ----

def test_single_workflow():
    """测试单个 workflow 的聚合"""
    workflows = [_make_workflow("w1", ["VASP"])]

    groups = {}
    for w in workflows:
        sig = _get_tool_signature(w)
        groups.setdefault(sig, []).append(w)

    assert len(groups) == 1


def test_empty_workflow_list():
    """测试空 workflow 列表"""
    workflows = []
    groups = {}
    for w in workflows:
        sig = _get_tool_signature(w)
        groups.setdefault(sig, []).append(w)

    assert len(groups) == 0


def test_single_step_workflow():
    """测试只有一个步骤的 workflow"""
    w = _make_workflow("w1", ["VASP"])

    assert len(w.steps) == 1
    sig = _get_tool_signature(w)
    assert len(sig) == 1
