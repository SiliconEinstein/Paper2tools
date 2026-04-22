"""
Step3 批量输入模块 - 从 Step2 输出的 XML 文件中提取文本，拼接后送入 workflow 提取
"""

from pathlib import Path
from typing import List, Tuple
from lxml import etree


def load_enriched_xml_as_text(xml_path: Path) -> str:
    """
    从增强后的 reasoning_chain_refine.xml 中提取纯文本

    Args:
        xml_path: XML 文件路径

    Returns:
        提取的文本内容
    """
    with open(xml_path, 'r', encoding='utf-8') as f:
        xml_content = f.read()

    try:
        root = etree.fromstring(xml_content.encode('utf-8'))
    except Exception as e:
        print(f"  ✗ Failed to parse {xml_path.name}: {e}")
        return ""

    # 提取所有 conclusion_reasoning 块的文本
    text_parts = []

    for cr in root.findall('.//conclusion_reasoning'):
        conclusion_id = cr.get('conclusion_id', 'unknown')
        conclusion_title = cr.get('conclusion_title', '')

        # 提取 conclusion 文本
        conclusion_elem = cr.find('conclusion')
        if conclusion_elem is not None and conclusion_elem.text:
            text_parts.append(f"## Conclusion: {conclusion_title}\n{conclusion_elem.text}\n")

        # 提取 reasoning 中的所有 step
        reasoning_elem = cr.find('reasoning')
        if reasoning_elem is not None:
            text_parts.append("### Reasoning Steps:\n")
            for step in reasoning_elem.findall('step'):
                step_id = step.get('id', '')
                step_text = step.text or ""

                # 提取工具引用
                tools = []
                for ref in step.findall('ref[@type="tool"]'):
                    tool_name = ref.text or ""
                    if tool_name:
                        tools.append(tool_name)

                tool_str = f" [Tools: {', '.join(tools)}]" if tools else ""
                text_parts.append(f"- Step {step_id}: {step_text}{tool_str}\n")

        # 提取 tools 总结
        tools_elem = cr.find('tools')
        if tools_elem is not None:
            text_parts.append("\n### Tools Used:\n")
            for tool in tools_elem.findall('tool'):
                name_elem = tool.find('tool_name')
                desc_elem = tool.find('tool_description')
                if name_elem is not None and name_elem.text:
                    tool_name = name_elem.text
                    tool_desc = desc_elem.text if desc_elem is not None else ""
                    text_parts.append(f"- **{tool_name}**: {tool_desc}\n")

        text_parts.append("\n---\n\n")

    return "".join(text_parts)


def load_texts_from_step2_output(step2_output_dir: Path) -> List[Tuple[str, str]]:
    """
    从 Step2 输出目录加载所有增强后的 XML 文件，转换为文本

    Args:
        step2_output_dir: Step2 输出目录

    Returns:
        [(text, source_id), ...] 列表
    """
    if not step2_output_dir.exists():
        raise FileNotFoundError(f"Step2 output directory not found: {step2_output_dir}")

    results = []
    xml_files = sorted(step2_output_dir.glob("*_reasoning_chain_refine.xml"))

    print(f"\n=== Loading Step2 Output for Step3 ===")
    print(f"Found {len(xml_files)} XML files in {step2_output_dir}")

    for xml_path in xml_files:
        text = load_enriched_xml_as_text(xml_path)
        if text:
            source_id = xml_path.stem.replace("_reasoning_chain_refine", "")
            results.append((text, source_id))

    print(f"  ✓ Loaded {len(results)} texts")

    return results
