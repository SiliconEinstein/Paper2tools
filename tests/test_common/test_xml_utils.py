"""
测试 XML 工具模块

测试内容:
- reasoning_chain.xml 解析
- <step> 节点提取
- <conclusion> 节点提取
- XML 序列化（格式保持）
- 步骤纯文本提取（去除子标签）
- 异常处理（格式错误的 XML）
"""

import pytest
from lxml import etree


# 测试用 XML 数据
SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<reasoning_chains>
    <conclusion_reasoning conclusion_id="c1" conclusion_title="Test Conclusion">
        <conclusion_text>This is a test conclusion.</conclusion_text>
        <reasoning>
            <step id="s1">First step with <ref type="citation">citation</ref></step>
            <step id="s2">Second step with <ref type="figure">figure</ref></step>
        </reasoning>
    </conclusion_reasoning>
</reasoning_chains>
"""

INVALID_XML = """<?xml version="1.0" encoding="UTF-8"?>
<reasoning_chains>
    <conclusion_reasoning>
        <step id="s1">Unclosed step
    </conclusion_reasoning>
"""


def test_parse_valid_xml():
    """测试解析有效的 XML"""
    root = etree.fromstring(SAMPLE_XML.encode('utf-8'))
    assert root.tag == "reasoning_chains"

    conclusions = root.findall(".//conclusion_reasoning")
    assert len(conclusions) == 1
    assert conclusions[0].get("conclusion_id") == "c1"


def test_parse_invalid_xml():
    """测试解析无效的 XML 应抛出异常"""
    with pytest.raises(etree.XMLSyntaxError):
        etree.fromstring(INVALID_XML.encode('utf-8'))


def test_extract_steps():
    """测试提取所有 <step> 节点"""
    root = etree.fromstring(SAMPLE_XML.encode('utf-8'))
    steps = root.findall(".//step")

    assert len(steps) == 2
    assert steps[0].get("id") == "s1"
    assert steps[1].get("id") == "s2"


def test_extract_conclusion_text():
    """测试提取 conclusion_text"""
    root = etree.fromstring(SAMPLE_XML.encode('utf-8'))
    conclusion_text = root.find(".//conclusion_text")

    assert conclusion_text is not None
    assert conclusion_text.text == "This is a test conclusion."


def test_get_step_pure_text():
    """测试获取步骤的纯文本（去除子标签）"""
    root = etree.fromstring(SAMPLE_XML.encode('utf-8'))
    step = root.find(".//step[@id='s1']")

    # 提取纯文本（包括子元素的 text 和 tail）
    text_parts = [step.text or ""]
    for child in step:
        text_parts.append(child.text or "")
        text_parts.append(child.tail or "")

    full_text = "".join(text_parts).strip()
    assert "First step" in full_text
    assert "citation" in full_text


def test_xml_serialization():
    """测试 XML 序列化保持格式"""
    root = etree.fromstring(SAMPLE_XML.encode('utf-8'))
    serialized = etree.tostring(root, encoding='unicode', pretty_print=True)

    assert "conclusion_reasoning" in serialized
    assert 'conclusion_id="c1"' in serialized
    assert "<step" in serialized


def test_add_new_element():
    """测试向 XML 添加新元素"""
    root = etree.fromstring(SAMPLE_XML.encode('utf-8'))
    step = root.find(".//step[@id='s1']")

    # 添加新的 <ref> 元素
    new_ref = etree.Element("ref")
    new_ref.set("type", "tool")
    new_ref.text = "TestTool"
    step.append(new_ref)

    # 验证添加成功
    refs = step.findall("ref")
    assert len(refs) == 2  # 原有 1 个 + 新增 1 个
    assert refs[-1].get("type") == "tool"
    assert refs[-1].text == "TestTool"


def test_modify_attribute():
    """测试修改 XML 属性"""
    root = etree.fromstring(SAMPLE_XML.encode('utf-8'))
    cr = root.find(".//conclusion_reasoning")

    # 修改属性
    cr.set("conclusion_id", "c2")
    assert cr.get("conclusion_id") == "c2"


def test_empty_xml():
    """测试空 XML 结构"""
    empty_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <reasoning_chains></reasoning_chains>
    """
    root = etree.fromstring(empty_xml.encode('utf-8'))

    conclusions = root.findall(".//conclusion_reasoning")
    assert len(conclusions) == 0


def test_xml_with_special_characters():
    """测试包含特殊字符的 XML"""
    special_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <reasoning_chains>
        <step id="s1">Text with &lt; &gt; &amp; special chars</step>
    </reasoning_chains>
    """
    root = etree.fromstring(special_xml.encode('utf-8'))
    step = root.find(".//step")

    assert "< >" in step.text
    assert "&" in step.text
