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
from src.step3.data_loader import WorkflowLoadItem, load_text, load_texts


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
    assert isinstance(results[0], WorkflowLoadItem)
    assert results[0].text == "Content"
    assert results[0].source_id == "single"


def test_load_texts_directory(tmp_path):
    """测试 load_texts 加载目录"""
    (tmp_path / "a.txt").write_text("Text A", encoding='utf-8')
    (tmp_path / "b.xml").write_text("<xml>B</xml>", encoding='utf-8')
    (tmp_path / "c.py").write_text("# ignored", encoding='utf-8')  # 不在支持列表中

    results = load_texts(tmp_path, mode="raw")

    assert len(results) == 2  # 只加载 .txt 和 .xml
    texts = [r.text for r in results]
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


def test_load_texts_selected_chains_prefers_step2_enrich(tmp_path):
    """selected_chains + 本地 Step2 refine：正文优先来自 XML（含工具结构），非 chain_text。"""
    s2 = tmp_path / "step2_out"
    s2.mkdir()
    xml = s2 / "paperA_reasoning_chain_refine.xml"
    xml.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<root>
  <conclusion_reasoning conclusion_id="c1">
    <conclusion title="T1">concl body</conclusion>
    <reasoning>
      <step id="1">from xml</step>
    </reasoning>
    <tools><tool tool_id="T1" index="1"><tool_name>X</tool_name><tool_description>d</tool_description></tool></tools>
  </conclusion_reasoning>
</root>""",
        encoding="utf-8",
    )
    p = tmp_path / "selected_chains.json"
    data = [
        {
            "chain_id": "paperA_c1",
            "cluster_id": 1,
            "paper_id": "paperA",
            "chain_text": "RAW_STEP1_ONLY",
        },
    ]
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    items = load_texts(p, mode="auto", step2_enriched_dir=s2)
    assert len(items) == 1
    assert items[0].source_id == "cluster_1"
    assert "from xml" in items[0].text
    assert "### Tools Used:" in items[0].text
    assert "RAW_STEP1_ONLY" not in items[0].text


def test_load_texts_selected_chains_prefers_tos_enrich(tmp_path):
    """selected_chains + TOS 配置：正文来自 download 的 refine XML，非 chain_text。"""
    xml_body = """<?xml version="1.0" encoding="UTF-8"?>
<root>
  <conclusion_reasoning conclusion_id="c1">
    <conclusion title="T1">from tos</conclusion>
    <reasoning>
      <step id="1">tos body</step>
    </reasoning>
    <tools><tool tool_id="T1" index="1"><tool_name>Y</tool_name><tool_description>e</tool_description></tool></tools>
  </conclusion_reasoning>
</root>"""
    p = tmp_path / "selected_chains.json"
    data = [
        {
            "chain_id": "paperA_c1",
            "cluster_id": 1,
            "paper_id": "paperA",
            "chain_text": "RAW_STEP1_ONLY",
        },
    ]
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    tos_cfg = {"output_prefix": "paper_ocr/tools/v2/reasoning_chain_refine/", "bucket": "wenyon-paper"}
    with patch("src.step2.data_loader.download_text", return_value=xml_body), patch(
        "src.step2.data_loader.get_tos_client", return_value=MagicMock()
    ), patch("src.step2.data_loader._tos_bucket", return_value="wenyon-paper"):
        items = load_texts(p, mode="auto", step2_enrich_tos=tos_cfg)

    assert len(items) == 1
    assert items[0].source_id == "cluster_1"
    assert "tos body" in items[0].text
    assert "RAW_STEP1_ONLY" not in items[0].text


def test_resolve_step3_tos_enrich_config():
    from src.step3.pipeline import resolve_step3_tos_enrich_config

    assert resolve_step3_tos_enrich_config({}) is None
    assert resolve_step3_tos_enrich_config({"step2_enrich_from_tos": False}) is None
    cfg = {
        "step2_enrich_from_tos": True,
        "tos": {"output_prefix": "paper_ocr/tools/v2/reasoning_chain_refine/"},
    }
    got = resolve_step3_tos_enrich_config(cfg)
    assert got["output_prefix"] == "paper_ocr/tools/v2/reasoning_chain_refine/"


def test_load_texts_selected_chains_json_auto(tmp_path):
    """Step1 selected_chains.json：按 cluster_id 分组，每簇一条输入"""
    import json

    p = tmp_path / "selected_chains.json"
    data = [
        {
            "chain_id": "paperA_c1",
            "cluster_id": 1,
            "distance": 0.2,
            "paper_id": "paperA",
            "chain_text": "second cluster text A",
        },
        {
            "chain_id": "paperB_c1",
            "cluster_id": 1,
            "distance": 0.1,
            "paper_id": "paperB",
            "chain_text": "second cluster text B",
        },
        {
            "chain_id": "paperC_c2",
            "cluster_id": 0,
            "distance": 0.05,
            "paper_id": "paperC",
            "chain_text": "first cluster only",
        },
    ]
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    items = load_texts(p, mode="auto")
    assert len(items) == 2
    assert items[0].source_id == "cluster_0"
    assert items[1].source_id == "cluster_1"
    assert items[0].provenance is not None
    assert items[0].provenance["cluster_id"] == 0
    assert len(items[0].provenance["members"]) == 1
    assert items[1].provenance["n_chains"] == 2
    assert "paperC" in items[0].text
    assert "paperA" in items[1].text and "paperB" in items[1].text


def test_load_texts_other_json_single_item(tmp_path):
    """非 selected_chains 形态的 JSON 仍按整文件一条处理"""
    import json

    p = tmp_path / "config_like.json"
    p.write_text(json.dumps({"foo": 1, "bar": [1, 2]}), encoding="utf-8")
    items = load_texts(p, mode="auto")
    assert len(items) == 1
    assert items[0].source_id == "config_like"
    assert items[0].provenance is None


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
    assert (tmp_path / "workflows_index.json").exists()
    assert (tmp_path / "workflows" / "w1.json").exists()


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

    assert (tmp_path / "workflows" / "w1.json").exists()
    assert (tmp_path / "workflows" / "w2.json").exists()

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
    (tmp_path / "workflows").mkdir()
    (tmp_path / "workflows" / "stale.json").write_text("{}", encoding="utf-8")
    save_workflows([], tmp_path)

    with open(tmp_path / "workflows.json") as f:
        library = json.load(f)
    assert library == []
    assert not list((tmp_path / "workflows").glob("*.json"))

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
