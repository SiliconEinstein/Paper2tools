"""
XML 增强模块 - 在 reasoning_chain.xml 中注入工具引用
"""

from lxml import etree
from typing import Dict, List


def enrich_reasoning_xml(
    original_xml: str,
    tools_by_conclusion: Dict[str, Dict]
) -> str:
    """
    在 reasoning_chain.xml 中注入工具信息

    Args:
        original_xml: 原始 XML 字符串
        tools_by_conclusion: {conclusion_id: {"tools": [...], "links": [...]}}

    Returns:
        增强后的 XML 字符串
    """
    root = etree.fromstring(original_xml.encode("utf-8"))

    for cr in root.findall(".//conclusion_reasoning"):
        conclusion_id = cr.get("conclusion_id", "")
        if conclusion_id not in tools_by_conclusion:
            continue

        data = tools_by_conclusion[conclusion_id]
        tools = data.get("tools", [])
        links = data.get("links", [])

        # 构建 step_id -> tool_ids 映射
        step_to_tools = {}
        for link in links:
            step_id = link.get("step_id", "")
            tool_id = link.get("tool_id", "")
            if step_id and tool_id:
                step_to_tools.setdefault(step_id, []).append(tool_id)

        # 构建 tool_id -> tool_info 映射
        tool_info_map = {t["tool_id"]: t for t in tools}

        # 在每个 <step> 末尾插入 <ref type="tool">
        reasoning = cr.find("reasoning")
        if reasoning is not None:
            for step in reasoning.findall("step"):
                step_id = step.get("id", "")
                if step_id not in step_to_tools:
                    continue

                for tool_id in step_to_tools[step_id]:
                    tool_info = tool_info_map.get(tool_id)
                    if not tool_info:
                        continue

                    ref = etree.Element("ref")
                    ref.set("type", "tool")
                    ref.set("tool_id", tool_id)
                    ref.text = tool_info["tool_name"]

                    # 插入到 step 末尾（在所有子元素之后）
                    step.append(ref)

        # 在 <conclusion_reasoning> 末尾添加 <tools> 节点
        if tools:
            tools_elem = etree.Element("tools")
            for tool_info in tools:
                tool_elem = etree.SubElement(tools_elem, "tool")

                name_elem = etree.SubElement(tool_elem, "tool_name")
                name_elem.text = tool_info["tool_name"]

                desc_elem = etree.SubElement(tool_elem, "tool_description")
                desc_elem.text = tool_info["tool_description"]

            cr.append(tools_elem)

    # 格式化输出
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + etree.tostring(
        root,
        encoding="unicode",
        pretty_print=True,
    )


def validate_enriched_xml(xml_text: str) -> bool:
    """验证增强后的 XML 格式是否正确"""
    try:
        etree.fromstring(xml_text.encode("utf-8"))
        return True
    except Exception:
        return False
