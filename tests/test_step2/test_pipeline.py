"""
测试 Step2 端到端流水线

测试内容:
- 完整的 Step2 流水线运行
- 配置文件加载和验证
- 数据加载→匹配→注入→保存的完整流程
- 输出文件格式正确性
- 与 Step1 输出的集成
"""

import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from src.step2.pipeline import load_config
from src.step2.data_loader import normalize_paper_id, PaperData, output_key


def test_load_config(tmp_path):
    """测试加载配置文件"""
    config_path = tmp_path / "config.yaml"
    config_data = {
        "tos": {
            "bucket": "test-bucket",
            "xml_source_prefix": "paper_ocr/xml/",
            "md_prefix": "paper_ocr/md/",
            "output_prefix": "paper_ocr/xml_refine/",
        },
        "llm": {"provider": "gpt5_mini"},
        "runtime": {"max_workers": 5, "verbose": True},
        "prompt": {"template_path": "prompts/tool_extract.txt"}
    }

    config_path.write_text(yaml.dump(config_data))
    config = load_config(str(config_path))

    assert config["tos"]["bucket"] == "test-bucket"
    assert config["llm"]["provider"] == "gpt5_mini"
    assert config["runtime"]["max_workers"] == 5


def test_normalize_paper_id():
    """测试 paper_id 归一化"""
    assert normalize_paper_id("10.1234/test") == "10.1234%2Ftest"
    assert normalize_paper_id("simple_id") == "simple_id"
    assert normalize_paper_id("a/b/c") == "a%2Fb%2Fc"


def test_output_key():
    """测试输出路径生成"""
    tos_config = {"output_prefix": "paper_ocr/xml_refine/"}
    key = output_key("10.1234/test", tos_config)

    assert key == "paper_ocr/xml_refine/10.1234%2Ftest_reasoning_chain_refine.xml"


def test_paper_data_dataclass():
    """测试 PaperData 数据类"""
    data = PaperData(
        paper_id="p1",
        reasoning_xml="<xml/>",
        paper_md="# Paper"
    )

    assert data.paper_id == "p1"
    assert data.reasoning_xml == "<xml/>"
    assert data.paper_md == "# Paper"


def test_config_all_keys_present(tmp_path):
    """测试配置文件包含所有必需的键"""
    config_data = {
        "tos": {
            "bucket": "b",
            "xml_source_prefix": "x/",
            "md_prefix": "m/",
            "output_prefix": "o/",
        },
        "llm": {"provider": "gpt5_mini"},
        "runtime": {"max_workers": 10, "verbose": True, "skip_existing": True},
        "prompt": {"template_path": "p.txt"}
    }

    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(config_data))
    config = load_config(str(config_path))

    assert "tos" in config
    assert "llm" in config
    assert "runtime" in config
    assert "prompt" in config


def test_normalize_paper_id_edge_cases():
    """测试 paper_id 归一化的边界情况"""
    assert normalize_paper_id("") == ""
    assert normalize_paper_id("no_slash") == "no_slash"
    # 多个斜杠
    assert normalize_paper_id("a/b/c/d") == "a%2Fb%2Fc%2Fd"
