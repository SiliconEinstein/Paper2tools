"""
测试工作流提取模块

测试内容:
- 从 ptlink 提取工具链
- 从增强 XML 提取工具序列
- workflow 实例的构建
- workflow 签名计算
- 边界情况（空工具链、单工具、复杂 DAG）
"""

import json
import pytest
from unittest.mock import patch, AsyncMock

from src.step3.workflow_extractor import _build_extraction_prompt, _parse_llm_response
from src.step3.schema import Workflow, WorkflowStep, IOSchema, IOField


# ---- prompt 构建测试 ----

def test_build_extraction_prompt():
    """测试 prompt 构建"""
    text = "Sample research text about using DFT and LAMMPS"
    prompt = _build_extraction_prompt(text)

    assert "Sample research text" in prompt
    assert "workflow" in prompt.lower()
    assert "JSON" in prompt


def test_prompt_contains_schema():
    """测试 prompt 包含输出 schema"""
    prompt = _build_extraction_prompt("test")

    assert "workflow_id" in prompt
    assert "title" in prompt
    assert "steps" in prompt
    assert "io_schema" in prompt
    assert "tool_refs" in prompt
    assert "column_hints" in prompt
    assert "benchmarks" in prompt


# ---- LLM 响应解析测试 ----

def test_parse_plain_json():
    """测试解析普通 JSON 响应"""
    response = json.dumps({
        "workflow_id": "w1",
        "title": "Test Workflow",
        "description": "A test",
        "steps": []
    })

    data = _parse_llm_response(response)

    assert data["workflow_id"] == "w1"
    assert data["title"] == "Test Workflow"


def test_parse_markdown_wrapped_json():
    """测试解析 markdown 包裹的 JSON"""
    response = """```json
{
    "workflow_id": "w1",
    "title": "Test",
    "description": "Test",
    "steps": []
}
```"""
    data = _parse_llm_response(response)
    assert data["workflow_id"] == "w1"


def test_parse_code_block_json():
    """测试解析代码块包裹的 JSON"""
    response = """```
{"workflow_id": "w1", "title": "Test", "description": "Test", "steps": []}
```"""
    data = _parse_llm_response(response)
    assert data["workflow_id"] == "w1"


def test_parse_invalid_json():
    """测试解析无效 JSON"""
    with pytest.raises(ValueError, match="JSON 解析失败"):
        _parse_llm_response("not a json at all")


def test_parse_whitespace_json():
    """测试解析带前后空白的 JSON"""
    response = """
    {"workflow_id": "w1", "title": "Test", "description": "Test", "steps": []}
    """
    data = _parse_llm_response(response)
    assert data["workflow_id"] == "w1"


# ---- Workflow 数据结构测试 ----

def test_workflow_from_dict():
    """测试从字典构建 Workflow"""
    data = {
        "workflow_id": "w1",
        "title": "DFT Workflow",
        "description": "A typical DFT calculation workflow",
        "source_ids": ["paper1"],
        "steps": [
            {
                "step_id": 1,
                "logic_description": "Prepare input structure",
                "tool_intent": "Structure preparation",
                "suggested_tools": ["VESTA"],
                "io_schema": {
                    "inputs": [{"name": "cif_file", "type": "file", "description": "CIF structure"}],
                    "outputs": [{"name": "poscar", "type": "file", "description": "POSCAR file"}]
                }
            }
        ]
    }

    workflow = Workflow.from_dict(data)

    assert workflow.workflow_id == "w1"
    assert workflow.title == "DFT Workflow"
    assert len(workflow.steps) == 1
    assert workflow.steps[0].suggested_tools == ["VESTA"]


def test_workflow_to_dict():
    """测试 Workflow 序列化为字典"""
    workflow = Workflow(
        workflow_id="w1",
        title="Test",
        description="Test workflow",
        source_ids=["s1"],
        steps=[
            WorkflowStep(
                step_id=1,
                logic_description="Step 1",
                tool_intent="Intent 1",
                suggested_tools=["Tool A"],
                io_schema=IOSchema(
                    inputs=[IOField(name="in1", type="str", description="Input 1")],
                    outputs=[]
                )
            )
        ]
    )

    d = workflow.to_dict()

    assert d["workflow_id"] == "w1"
    assert len(d["steps"]) == 1
    assert d["steps"][0]["suggested_tools"] == ["Tool A"]
    assert len(d["steps"][0]["io_schema"]["inputs"]) == 1


def test_workflow_empty_steps():
    """测试空步骤的 Workflow"""
    workflow = Workflow(
        workflow_id="w1",
        title="Empty",
        description="No steps",
        source_ids=[],
        steps=[]
    )

    assert len(workflow.steps) == 0
    d = workflow.to_dict()
    assert d["steps"] == []


def test_workflow_roundtrip():
    """测试 Workflow 序列化/反序列化往返"""
    original = Workflow(
        workflow_id="w1",
        title="Test",
        description="Desc",
        source_ids=["s1", "s2"],
        steps=[
            WorkflowStep(
                step_id=1,
                logic_description="First step",
                tool_intent="Tool intent",
                suggested_tools=["VASP", "LAMMPS"],
                io_schema=IOSchema(
                    inputs=[IOField("in1", "str", "desc")],
                    outputs=[IOField("out1", "float", "desc")]
                )
            ),
            WorkflowStep(
                step_id=2,
                logic_description="Second step",
                tool_intent="Another intent",
            )
        ]
    )

    d = original.to_dict()
    restored = Workflow.from_dict(d)

    assert restored.workflow_id == original.workflow_id
    assert restored.title == original.title
    assert len(restored.steps) == len(original.steps)
    assert restored.steps[0].suggested_tools == original.steps[0].suggested_tools


def test_io_field():
    """测试 IOField 数据结构"""
    field = IOField(name="input1", type="float", description="A float input")

    d = field.to_dict()
    assert d == {"name": "input1", "type": "float", "description": "A float input"}

    restored = IOField.from_dict(d)
    assert restored.name == "input1"
    assert restored.type == "float"


def test_io_field_column_hints_roundtrip():
    field = IOField(
        name="counts",
        type="table",
        description="gene x cell",
        column_hints=["gene_id", "umi_count"],
    )
    restored = IOField.from_dict(field.to_dict())
    assert restored.column_hints == ["gene_id", "umi_count"]


def test_workflow_optional_top_level_roundtrip():
    data = {
        "workflow_id": "w_x",
        "title": "T",
        "description": "D",
        "source_ids": [],
        "keywords": ["a", "b"],
        "research_questions": ["How can I run QC?"],
        "datasets": [{"dataset_id": "GSE1", "source_type": "GEO", "accession_or_url": "", "description": "x", "note": ""}],
        "benchmarks": [{"benchmark_id": "bm1", "metric": "m", "linked_step_id": 1, "expected_direction": "higher_is_better", "acceptance_criteria": "", "how_to_compute": ""}],
        "steps": [
            {
                "step_id": 1,
                "step_name": "step_one",
                "logic_description": "L",
                "tool_intent": "I",
                "parameters": ["k=2"],
                "tool_refs": ["Tool v1 (https://example.com)"],
                "suggested_tools": ["Tool"],
                "io_schema": {"inputs": [], "outputs": []},
            }
        ],
    }
    wf = Workflow.from_dict(data)
    back = Workflow.from_dict(wf.to_dict())
    assert back.keywords == ["a", "b"]
    assert back.steps[0].step_name == "step_one"
    assert back.steps[0].parameters == ["k=2"]
    assert len(back.datasets) == 1


def test_io_schema():
    """测试 IOSchema 数据结构"""
    schema = IOSchema(
        inputs=[IOField("in1", "str", "input")],
        outputs=[IOField("out1", "int", "output")]
    )

    d = schema.to_dict()
    assert len(d["inputs"]) == 1
    assert len(d["outputs"]) == 1

    restored = IOSchema.from_dict(d)
    assert restored.inputs[0].name == "in1"


def test_workflow_step_defaults():
    """测试 WorkflowStep 默认值"""
    step = WorkflowStep(
        step_id=1,
        logic_description="Test",
        tool_intent="Intent"
    )

    assert step.suggested_tools == []
    assert step.io_schema.inputs == []
    assert step.io_schema.outputs == []
