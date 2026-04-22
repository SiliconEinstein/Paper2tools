"""
测试 XML 增强模块

测试内容:
- <ref type="tool"> 标签的正确注入
- <tools> 汇总节点的生成
- XML 格式保持（缩进、属性顺序）
- 增强后 XML 的合法性验证
- 边界情况（空步骤、已有工具引用）
"""

import pytest
from lxml import etree
from src.step2.xml_enricher import enrich_reasoning_xml, validate_enriched_xml


SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<reasoning_chains>
    <conclusion_reasoning conclusion_id="c1" conclusion_title="Test Conclusion">
        <conclusion_text>Conclusion text.</conclusion_text>
        <reasoning>
            <step id="s1">First step using DFT calculation</step>
            <step id="s2">Second step analyzing results</step>
        </reasoning>
    </conclusion_reasoning>
</reasoning_chains>
"""

MULTI_CONCLUSION_XML = """<?xml version="1.0" encoding="UTF-8"?>
<reasoning_chains>
    <conclusion_reasoning conclusion_id="c1" conclusion_title="Conclusion 1">
        <reasoning>
            <step id="s1">Step 1</step>
        </reasoning>
    </conclusion_reasoning>
    <conclusion_reasoning conclusion_id="c2" conclusion_title="Conclusion 2">
        <reasoning>
            <step id="s2">Step 2</step>
        </reasoning>
    </conclusion_reasoning>
</reasoning_chains>
"""


@pytest.fixture
def sample_tools_by_conclusion():
    """测试用的工具匹配数据"""
    return {
        "c1": {
            "tools": [
                {"tool_id": "t1", "tool_name": "VASP", "tool_description": "DFT software"},
                {"tool_id": "t2", "tool_name": "Matplotlib", "tool_description": "Plotting library"},
            ],
            "links": [
                {"step_id": "s1", "tool_id": "t1"},
                {"step_id": "s2", "tool_id": "t2"},
            ]
        }
    }


def test_inject_tool_refs(sample_tools_by_conclusion):
    """测试注入 <ref type="tool"> 标签"""
    result = enrich_reasoning_xml(SAMPLE_XML, sample_tools_by_conclusion)

    root = etree.fromstring(result.encode('utf-8'))
    refs = root.findall('.//ref[@type="tool"]')

    assert len(refs) == 2
    # 验证 s1 步骤关联了 VASP
    step1 = root.find('.//step[@id="s1"]')
    step1_refs = step1.findall('ref[@type="tool"]')
    assert len(step1_refs) == 1
    assert step1_refs[0].text == "VASP"
    assert step1_refs[0].get("tool_id") == "t1"


def test_add_tools_summary(sample_tools_by_conclusion):
    """测试添加 <tools> 汇总节点"""
    result = enrich_reasoning_xml(SAMPLE_XML, sample_tools_by_conclusion)

    root = etree.fromstring(result.encode('utf-8'))
    tools_elem = root.find('.//conclusion_reasoning[@conclusion_id="c1"]/tools')

    assert tools_elem is not None
    tool_elems = tools_elem.findall('tool')
    assert len(tool_elems) == 2

    names = [t.find('tool_name').text for t in tool_elems]
    assert "VASP" in names
    assert "Matplotlib" in names


def test_xml_validity_after_enrichment(sample_tools_by_conclusion):
    """测试增强后 XML 的合法性"""
    result = enrich_reasoning_xml(SAMPLE_XML, sample_tools_by_conclusion)
    assert validate_enriched_xml(result)


def test_no_tools_for_conclusion():
    """测试没有工具匹配的 conclusion"""
    tools_by_conclusion = {}  # 空映射
    result = enrich_reasoning_xml(SAMPLE_XML, tools_by_conclusion)

    # 不应该有 tool ref
    root = etree.fromstring(result.encode('utf-8'))
    refs = root.findall('.//ref[@type="tool"]')
    assert len(refs) == 0


def test_empty_links():
    """测试有工具但没有 link 的情况"""
    tools_by_conclusion = {
        "c1": {
            "tools": [{"tool_id": "t1", "tool_name": "VASP", "tool_description": "DFT"}],
            "links": []  # 没有 link
        }
    }
    result = enrich_reasoning_xml(SAMPLE_XML, tools_by_conclusion)

    root = etree.fromstring(result.encode('utf-8'))
    refs = root.findall('.//ref[@type="tool"]')
    assert len(refs) == 0  # 没有 link 就不注入 ref

    # 但 tools 汇总节点仍然存在
    tools_elem = root.find('.//tools')
    assert tools_elem is not None


def test_multi_conclusion(sample_tools_by_conclusion):
    """测试多个 conclusion 的处理"""
    tools = {
        "c1": {
            "tools": [{"tool_id": "t1", "tool_name": "VASP", "tool_description": "DFT"}],
            "links": [{"step_id": "s1", "tool_id": "t1"}]
        },
        "c2": {
            "tools": [{"tool_id": "t2", "tool_name": "LAMMPS", "tool_description": "MD"}],
            "links": [{"step_id": "s2", "tool_id": "t2"}]
        }
    }

    result = enrich_reasoning_xml(MULTI_CONCLUSION_XML, tools)
    root = etree.fromstring(result.encode('utf-8'))

    # 两个 conclusion 都应该有 tools
    all_tools = root.findall('.//tools')
    assert len(all_tools) == 2


def test_step_with_multiple_tools():
    """测试一个步骤关联多个工具"""
    tools_by_conclusion = {
        "c1": {
            "tools": [
                {"tool_id": "t1", "tool_name": "VASP", "tool_description": "DFT"},
                {"tool_id": "t2", "tool_name": "LAMMPS", "tool_description": "MD"},
            ],
            "links": [
                {"step_id": "s1", "tool_id": "t1"},
                {"step_id": "s1", "tool_id": "t2"},  # 同一步骤两个工具
            ]
        }
    }

    result = enrich_reasoning_xml(SAMPLE_XML, tools_by_conclusion)
    root = etree.fromstring(result.encode('utf-8'))

    step1 = root.find('.//step[@id="s1"]')
    refs = step1.findall('ref[@type="tool"]')
    assert len(refs) == 2


def test_validate_valid_xml():
    """测试验证有效 XML"""
    assert validate_enriched_xml(SAMPLE_XML) is True


def test_validate_invalid_xml():
    """测试验证无效 XML"""
    assert validate_enriched_xml("<unclosed>") is False
    assert validate_enriched_xml("not xml at all") is False


def test_unknown_conclusion_id():
    """测试工具映射中包含不存在的 conclusion_id"""
    tools_by_conclusion = {
        "c_nonexistent": {
            "tools": [{"tool_id": "t1", "tool_name": "VASP", "tool_description": "DFT"}],
            "links": [{"step_id": "s1", "tool_id": "t1"}]
        }
    }
    result = enrich_reasoning_xml(SAMPLE_XML, tools_by_conclusion)

    # 不匹配的 conclusion_id 不影响其他部分
    root = etree.fromstring(result.encode('utf-8'))
    refs = root.findall('.//ref[@type="tool"]')
    assert len(refs) == 0


def test_preserve_existing_refs():
    """测试保留已有的 ref 标签"""
    xml_with_refs = """<?xml version="1.0" encoding="UTF-8"?>
    <reasoning_chains>
        <conclusion_reasoning conclusion_id="c1" conclusion_title="Test">
            <reasoning>
                <step id="s1">Step with <ref type="citation">cite1</ref></step>
            </reasoning>
        </conclusion_reasoning>
    </reasoning_chains>
    """
    tools_by_conclusion = {
        "c1": {
            "tools": [{"tool_id": "t1", "tool_name": "VASP", "tool_description": "DFT"}],
            "links": [{"step_id": "s1", "tool_id": "t1"}]
        }
    }

    result = enrich_reasoning_xml(xml_with_refs, tools_by_conclusion)
    root = etree.fromstring(result.encode('utf-8'))
    step1 = root.find('.//step[@id="s1"]')

    all_refs = step1.findall('ref')
    assert len(all_refs) == 2  # 原有 citation + 新增 tool
    types = {r.get("type") for r in all_refs}
    assert "citation" in types
    assert "tool" in types


def test_output_has_xml_declaration(sample_tools_by_conclusion):
    """测试输出包含 XML 声明"""
    result = enrich_reasoning_xml(SAMPLE_XML, sample_tools_by_conclusion)
    assert result.startswith('<?xml version="1.0" encoding="UTF-8"?>')
