"""
工具提取模块 - 用 LLM 从论文 MD 中提取每个 conclusion_reasoning 用到的工具
"""

import json
import re
from pathlib import Path
from typing import Dict, List

from lxml import etree


def _load_prompt_template(template_path: str) -> str:
    path = Path(template_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / template_path
    return path.read_text(encoding="utf-8")


def _build_prompt(template: str, conclusion_id: str, conclusion_title: str,
                  reasoning_xml: str, paper_content: str) -> str:
    return (template
            .replace("{{conclusion_id}}", conclusion_id)
            .replace("{{conclusion_title}}", conclusion_title)
            .replace("{{reasoning_xml}}", reasoning_xml)
            .replace("{{paper_content}}", paper_content))


def _parse_llm_response(response) -> Dict:
    """解析 LLM 返回的 JSON，容错处理（content 可能为 None）。"""
    if response is None:
        return {"tools": [], "links": []}
    if not isinstance(response, str):
        response = str(response)
    text = response.strip()
    # 去掉可能的 markdown 代码块
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 尝试提取第一个 JSON 对象
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"tools": [], "links": []}


def extract_conclusion_blocks(reasoning_xml: str) -> List[Dict]:
    """从 reasoning_chain.xml 中提取所有 conclusion_reasoning 块"""
    root = etree.fromstring(reasoning_xml.encode("utf-8"))
    blocks = []
    for cr in root.findall(".//conclusion_reasoning"):
        conclusion_id = cr.get("conclusion_id", "unknown")
        conclusion_elem = cr.find("conclusion")
        conclusion_title = conclusion_elem.get("title", "") if conclusion_elem is not None else ""
        reasoning_elem = cr.find("reasoning")
        reasoning_xml_str = etree.tostring(reasoning_elem, encoding="unicode") if reasoning_elem is not None else ""
        blocks.append({
            "conclusion_id": conclusion_id,
            "conclusion_title": conclusion_title,
            "reasoning_xml": reasoning_xml_str,
            "element": cr,
        })
    return blocks


async def extract_tools_for_conclusion(
    conclusion_id: str,
    conclusion_title: str,
    reasoning_xml: str,
    paper_md: str,
    prompt_template: str,
    llm_fn,
) -> Dict:
    """调用 LLM 提取单个 conclusion 的工具信息"""
    prompt = _build_prompt(
        prompt_template,
        conclusion_id=conclusion_id,
        conclusion_title=conclusion_title,
        reasoning_xml=reasoning_xml,
        paper_content=paper_md,
    )
    response = await llm_fn(prompt, temperature=0.0)
    result = _parse_llm_response(response)
    # 确保结构完整
    result.setdefault("tools", [])
    result.setdefault("links", [])
    return result
