"""
Step3 批量输入模块 - 从 Step2 输出的 XML 文件中提取文本，拼接后送入 workflow 提取
"""

from pathlib import Path
from typing import List, Optional, Tuple
from lxml import etree


def _conclusion_reasoning_element_to_text(cr: etree._Element) -> str:
    """将单个 <conclusion_reasoning> 子树转为与 load_enriched_xml_as_text 一致的纯文本。"""
    conclusion_title = cr.get("conclusion_title", "")
    text_parts: List[str] = []

    conclusion_elem = cr.find("conclusion")
    if conclusion_elem is not None:
        if conclusion_elem.get("title"):
            conclusion_title = conclusion_elem.get("title", "") or conclusion_title
        if conclusion_elem.text:
            text_parts.append(f"## Conclusion: {conclusion_title}\n{conclusion_elem.text}\n")

    reasoning_elem = cr.find("reasoning")
    if reasoning_elem is not None:
        text_parts.append("### Reasoning Steps:\n")
        for step in reasoning_elem.findall("step"):
            step_id = step.get("id", "")
            step_text = step.text or ""

            tools = []
            for ref in step.findall('ref[@type="tool"]'):
                tool_name = ref.text or ""
                if tool_name:
                    tools.append(tool_name)

            tool_str = f" [Tools: {', '.join(tools)}]" if tools else ""
            text_parts.append(f"- Step {step_id}: {step_text}{tool_str}\n")

    tools_elem = cr.find("tools")
    if tools_elem is not None:
        text_parts.append("\n### Tools Used:\n")
        for tool in tools_elem.findall("tool"):
            name_elem = tool.find("tool_name")
            desc_elem = tool.find("tool_description")
            if name_elem is not None and name_elem.text:
                tool_name = name_elem.text
                tool_desc = desc_elem.text if desc_elem is not None else ""
                text_parts.append(f"- **{tool_name}**: {tool_desc}\n")

    text_parts.append("\n---\n\n")
    return "".join(text_parts)


def try_extract_conclusion_from_refine_xml_string(
    xml_content: str, conclusion_id: str, *, source_label: str = ""
) -> Optional[str]:
    """从 refine XML 字符串中提取指定 conclusion_id 对应块。"""
    if not (xml_content and xml_content.strip() and conclusion_id):
        return None
    label = source_label or "xml"
    try:
        root = etree.fromstring(xml_content.encode("utf-8"))
    except Exception as e:
        print(f"  ✗ Failed to parse {label}: {e}", flush=True)
        return None

    for cr in root.findall(".//conclusion_reasoning"):
        cid = cr.get("conclusion_id")
        if cid is not None and str(cid) == str(conclusion_id):
            t = _conclusion_reasoning_element_to_text(cr)
            return t if t.strip() else None
    return None


def try_extract_conclusion_from_refine_xml(
    xml_path: Path, conclusion_id: str
) -> Optional[str]:
    """
    从单篇 refine XML 中提取指定 conclusion_id 对应块（含 Step2 注入的工具信息）。
    conclusion_id 通常与 selected_chains 中 chain_id 在 paper_id 前缀之后的后缀一致。
    """
    if not xml_path.is_file() or not conclusion_id:
        return None
    try:
        with open(xml_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError as e:
        print(f"  ✗ Failed to read {xml_path.name}: {e}", flush=True)
        return None
    return try_extract_conclusion_from_refine_xml_string(
        raw, conclusion_id, source_label=xml_path.name
    )


def load_enriched_xml_as_text_from_string(xml_content: str, *, source_label: str = "") -> str:
    """从 refine XML 字符串提取与 load_enriched_xml_as_text 一致的纯文本。"""
    label = source_label or "xml"
    try:
        root = etree.fromstring(xml_content.encode("utf-8"))
    except Exception as e:
        print(f"  ✗ Failed to parse {label}: {e}", flush=True)
        return ""

    text_parts: List[str] = []
    for cr in root.findall(".//conclusion_reasoning"):
        text_parts.append(_conclusion_reasoning_element_to_text(cr))

    return "".join(text_parts)


def load_enriched_xml_as_text(xml_path: Path) -> str:
    """
    从增强后的 reasoning_chain_refine.xml 中提取纯文本

    Args:
        xml_path: XML 文件路径

    Returns:
        提取的文本内容
    """
    with open(xml_path, "r", encoding="utf-8") as f:
        xml_content = f.read()

    return load_enriched_xml_as_text_from_string(xml_content, source_label=xml_path.name)


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
