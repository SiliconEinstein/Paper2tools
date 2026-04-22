"""
批量处理模块 - 将多条思维链拼接成文本，批量提取工具信息
"""

import asyncio
from pathlib import Path
from typing import List, Dict
from lxml import etree

from .data_loader import load_paper_data, get_tos_client
from .tool_extractor import extract_conclusion_blocks, extract_tools_for_conclusion, _load_prompt_template
from .xml_enricher import enrich_reasoning_xml, validate_enriched_xml


async def process_paper_batch(
    paper_ids: List[str],
    tos_config: dict,
    llm_fn,
    prompt_template: str,
    output_dir: Path,
    verbose: bool = True
) -> Dict:
    """
    批量处理多篇论文，拼接思维链文本并提取工具信息

    Args:
        paper_ids: 论文 ID 列表
        tos_config: TOS 配置
        llm_fn: LLM 函数
        prompt_template: Prompt 模板
        output_dir: 输出目录
        verbose: 是否打印详细信息

    Returns:
        处理结果统计
    """
    if verbose:
        print(f"\n=== Step2 Batch Processing ===")
        print(f"Processing {len(paper_ids)} papers...")

    # 1. 加载所有论文数据
    papers_data = []
    for i, paper_id in enumerate(paper_ids, 1):
        if verbose and i % 10 == 0:
            print(f"  Loading papers: {i}/{len(paper_ids)}")

        paper_data = await asyncio.to_thread(load_paper_data, paper_id, tos_config)
        if paper_data:
            papers_data.append(paper_data)

    if verbose:
        print(f"  ✓ Loaded {len(papers_data)}/{len(paper_ids)} papers")

    if not papers_data:
        return {"status": "failed", "reason": "no papers loaded"}

    # 2. 拼接所有思维链文本
    combined_xml_parts = []
    combined_md_parts = []

    for paper_data in papers_data:
        # 提取 reasoning_chain.xml 中的所有 conclusion_reasoning 块
        try:
            root = etree.fromstring(paper_data.reasoning_xml.encode("utf-8"))
            for cr in root.findall(".//conclusion_reasoning"):
                cr_str = etree.tostring(cr, encoding="unicode", pretty_print=True)
                combined_xml_parts.append(cr_str)
        except Exception as e:
            if verbose:
                print(f"  ✗ Failed to parse XML for {paper_data.paper_id}: {e}")
            continue

        # 论文 MD 文本（截取前 5000 字符避免过长）
        combined_md_parts.append(f"# Paper: {paper_data.paper_id}\n{paper_data.paper_md[:5000]}\n")

    combined_xml = "\n".join(combined_xml_parts)
    combined_md = "\n\n".join(combined_md_parts)

    if verbose:
        print(f"  ✓ Combined XML: {len(combined_xml)} chars")
        print(f"  ✓ Combined MD: {len(combined_md)} chars")

    # 3. 对每篇论文的每个 conclusion 提取工具
    results = []
    for paper_data in papers_data:
        blocks = extract_conclusion_blocks(paper_data.reasoning_xml)
        if not blocks:
            continue

        tools_by_conclusion = {}
        for block in blocks:
            result = await extract_tools_for_conclusion(
                conclusion_id=block["conclusion_id"],
                conclusion_title=block["conclusion_title"],
                reasoning_xml=block["reasoning_xml"],
                paper_md=combined_md,  # 使用拼接后的 MD
                prompt_template=prompt_template,
                llm_fn=llm_fn,
            )
            tools_by_conclusion[block["conclusion_id"]] = result

        # 4. 注入 XML
        enriched_xml = enrich_reasoning_xml(paper_data.reasoning_xml, tools_by_conclusion)

        if not validate_enriched_xml(enriched_xml):
            if verbose:
                print(f"  ✗ Invalid XML for {paper_data.paper_id}")
            continue

        # 5. 保存到本地
        output_path = output_dir / f"{paper_data.paper_id}_reasoning_chain_refine.xml"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(enriched_xml, encoding="utf-8")

        results.append({"paper_id": paper_data.paper_id, "status": "success"})

        if verbose:
            print(f"  ✓ {paper_data.paper_id}: {len(tools_by_conclusion)} conclusions processed")

    if verbose:
        print(f"\n✓ Batch processing complete: {len(results)}/{len(papers_data)} succeeded")

    return {
        "total": len(paper_ids),
        "loaded": len(papers_data),
        "success": len(results),
        "results": results
    }
