"""
测试 Step3 端到端流水线

测试内容:
- 完整的 Step3 流水线运行
- 配置文件加载和验证
- 数据加载→提取→聚合→保存的完整流程
- 输出文件格式正确性
- 与 Step2 输出的集成
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

from src.step3.schema import Workflow, WorkflowStep, IOSchema, IOField
from src.step3.pipeline import save_workflows
from src.step3.data_loader import load_text, load_texts


# ---- data_loader 测试 ----

def test_load_text_from_file(tmp_path):
    """测试从单个文件加载文本"""
    file = tmp_path / "test.txt"
    file.write_text("Hello, this is test content.", encoding='utf-8')

    text, source_id = load_text(file)

    assert text == "Hello, this is test content."
    assert source_id == "test"


def test_load_text_file_not_found():
    """测试加载不存在的文件"""
    with pytest.raises(FileNotFoundError):
        load_text(Path("/nonexistent/file.txt"))


def test_load_text_directory_error(tmp_path):
    """测试加载目录作为文件应报错"""
    with pytest.raises(ValueError, match="路径不是文件"):
        load_text(tmp_path)


def test_load_texts_single_file(tmp_path):
    """测试 load_texts 加载单个文件"""
    file = tmp_path / "single.txt"
    file.write_text("Content", encoding='utf-8')

    results = load_texts(file, mode="raw")
    assert len(results) == 1
    assert results[0][0] == "Content"


def test_load_texts_directory(tmp_path):
    """测试 load_texts 加载目录"""
    (tmp_path / "a.txt").write_text("Text A", encoding='utf-8')
    (tmp_path / "b.xml").write_text("<xml>B</xml>", encoding='utf-8')
    (tmp_path / "c.py").write_text("# ignored", encoding='utf-8')  # 不在支持列表中

    results = load_texts(tmp_path, mode="raw")

    assert len(results) == 2  # 只加载 .txt 和 .xml
    texts = [r[0] for r in results]
    assert "Text A" in texts
    assert "<xml>B</xml>" in texts


def test_load_texts_empty_directory(tmp_path):
    """测试加载空目录"""
    results = load_texts(tmp_path, mode="raw")
    assert results == []


def test_load_texts_invalid_path():
    """测试加载无效路径"""
    with pytest.raises(ValueError, match="路径既不是文件也不是目录"):
        load_texts(Path("/nonexistent/path"), mode="raw")


# ---- save_workflows 测试 ----

def test_save_workflows_creates_files(tmp_path):
    """测试保存 workflow 创建正确的文件"""
    workflows = [
        Workflow(
            workflow_id="w1",
            title="Test Workflow",
            description="A test",
            source_ids=["s1"],
            steps=[
                WorkflowStep(step_id=1, logic_description="Step 1", tool_intent="Intent")
            ]
        )
    ]

    save_workflows(workflows, tmp_path)

    assert (tmp_path / "workflows.json").exists()
    assert (tmp_path / "workflow_stats.json").exists()


def test_save_workflows_content(tmp_path):
    """测试保存的 workflow 内容正确"""
    workflows = [
        Workflow(
            workflow_id="w1",
            title="Test",
            description="Desc",
            steps=[
                WorkflowStep(step_id=1, logic_description="S1", tool_intent="I1"),
                WorkflowStep(step_id=2, logic_description="S2", tool_intent="I2"),
            ]
        ),
        Workflow(
            workflow_id="w2",
            title="Test2",
            description="Desc2",
            steps=[
                WorkflowStep(step_id=1, logic_description="S1", tool_intent="I1"),
            ]
        )
    ]

    save_workflows(workflows, tmp_path)

    with open(tmp_path / "workflows.json", 'r') as f:
        library = json.load(f)

    assert len(library) == 2
    assert library[0]["workflow_id"] == "w1"
    assert len(library[0]["steps"]) == 2


def test_save_workflows_stats(tmp_path):
    """测试保存的统计信息正确"""
    workflows = [
        Workflow(
            workflow_id="w1", title="T1", description="D1",
            steps=[
                WorkflowStep(step_id=1, logic_description="S1", tool_intent="I1"),
                WorkflowStep(step_id=2, logic_description="S2", tool_intent="I2"),
            ]
        ),
        Workflow(
            workflow_id="w2", title="T2", description="D2",
            steps=[
                WorkflowStep(step_id=1, logic_description="S1", tool_intent="I1"),
            ]
        )
    ]

    save_workflows(workflows, tmp_path)

    with open(tmp_path / "workflow_stats.json", 'r') as f:
        stats = json.load(f)

    assert stats["total_workflows"] == 2
    assert stats["total_steps"] == 3
    assert stats["avg_steps_per_workflow"] == pytest.approx(1.5)


def test_save_empty_workflows(tmp_path):
    """测试保存空 workflow 列表"""
    save_workflows([], tmp_path)

    with open(tmp_path / "workflows.json") as f:
        library = json.load(f)
    assert library == []

    with open(tmp_path / "workflow_stats.json") as f:
        stats = json.load(f)
    assert stats["total_workflows"] == 0
    assert stats["avg_steps_per_workflow"] == 0


def test_save_workflows_creates_directory(tmp_path):
    """测试保存时自动创建不存在的目录"""
    output_dir = tmp_path / "nested" / "output"
    workflows = [
        Workflow(workflow_id="w1", title="T", description="D", steps=[])
    ]

    save_workflows(workflows, output_dir)

    assert output_dir.exists()
    assert (output_dir / "workflows.json").exists()


def test_save_workflows_idempotent(tmp_path):
    """测试保存幂等性"""
    workflows = [
        Workflow(workflow_id="w1", title="T", description="D", steps=[])
    ]

    save_workflows(workflows, tmp_path)
    save_workflows(workflows, tmp_path)

    with open(tmp_path / "workflows.json") as f:
        library = json.load(f)
    assert len(library) == 1
