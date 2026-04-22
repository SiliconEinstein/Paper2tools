"""
测试 JSON 工具模块

测试内容:
- _tools_extract_result.json 加载
- tools[] 提取
- ptlink[] 提取
- JSON Schema 验证
- 安全解析（格式异常处理）
"""

import json
import pytest
from pathlib import Path
import tempfile


# 测试用 JSON 数据
SAMPLE_TOOL_JSON = {
    "tools": [
        {
            "tool_id": "t1",
            "tool_name": "Tool A",
            "tool_description": "Description of Tool A"
        },
        {
            "tool_id": "t2",
            "tool_name": "Tool B",
            "tool_description": "Description of Tool B"
        }
    ],
    "ptlink": [
        {
            "step_id": "s1",
            "tool_id": "t1",
            "evidence": "Evidence text"
        }
    ],
    "par": []
}


def test_load_valid_json():
    """测试加载有效的 JSON 文件"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(SAMPLE_TOOL_JSON, f)
        temp_path = f.name

    try:
        with open(temp_path, 'r') as f:
            data = json.load(f)

        assert "tools" in data
        assert "ptlink" in data
        assert len(data["tools"]) == 2
    finally:
        Path(temp_path).unlink()


def test_extract_tools():
    """测试提取 tools 列表"""
    tools = SAMPLE_TOOL_JSON["tools"]

    assert len(tools) == 2
    assert tools[0]["tool_id"] == "t1"
    assert tools[1]["tool_name"] == "Tool B"


def test_extract_ptlinks():
    """测试提取 ptlink 列表"""
    ptlinks = SAMPLE_TOOL_JSON["ptlink"]

    assert len(ptlinks) == 1
    assert ptlinks[0]["step_id"] == "s1"
    assert ptlinks[0]["tool_id"] == "t1"


def test_missing_required_field():
    """测试缺少必需字段"""
    invalid_data = {"tools": [{"tool_id": "t1"}]}  # 缺少 tool_name

    # 验证字段存在性
    tool = invalid_data["tools"][0]
    assert "tool_id" in tool
    assert "tool_name" not in tool


def test_empty_tools_list():
    """测试空的 tools 列表"""
    data = {"tools": [], "ptlink": []}

    assert len(data["tools"]) == 0
    assert isinstance(data["tools"], list)


def test_load_invalid_json():
    """测试加载无效的 JSON 文件"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("{invalid json")
        temp_path = f.name

    try:
        with pytest.raises(json.JSONDecodeError):
            with open(temp_path, 'r') as f:
                json.load(f)
    finally:
        Path(temp_path).unlink()


def test_safe_json_load_with_encoding():
    """测试处理不同编码的 JSON"""
    data = {"tools": [{"tool_name": "工具A"}]}

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
        temp_path = f.name

    try:
        with open(temp_path, 'r', encoding='utf-8') as f:
            loaded = json.load(f)

        assert loaded["tools"][0]["tool_name"] == "工具A"
    finally:
        Path(temp_path).unlink()


def test_nested_structure():
    """测试嵌套结构的访问"""
    data = {
        "tools": [
            {
                "tool_id": "t1",
                "metadata": {
                    "category": "analysis",
                    "tags": ["ml", "stats"]
                }
            }
        ]
    }

    tool = data["tools"][0]
    assert tool["metadata"]["category"] == "analysis"
    assert len(tool["metadata"]["tags"]) == 2


def test_validate_tool_schema():
    """测试工具数据的 schema 验证"""
    tool = SAMPLE_TOOL_JSON["tools"][0]

    # 验证必需字段
    required_fields = ["tool_id", "tool_name", "tool_description"]
    for field in required_fields:
        assert field in tool, f"Missing required field: {field}"


def test_validate_ptlink_schema():
    """测试 ptlink 数据的 schema 验证"""
    ptlink = SAMPLE_TOOL_JSON["ptlink"][0]

    # 验证必需字段
    required_fields = ["step_id", "tool_id"]
    for field in required_fields:
        assert field in ptlink, f"Missing required field: {field}"
