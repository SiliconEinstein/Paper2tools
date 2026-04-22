"""
Step2 主流程 - 加载数据 → LLM 提取工具 → 注入 XML → 上传 TOS
"""

import asyncio
import sys
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from .data_loader import load_paper_data, list_paper_ids, output_exists, upload_xml
from .tool_extractor import extract_conclusion_blocks, extract_tools_for_conclusion, _load_prompt_template
from .xml_enricher import enrich_reasoning_xml, validate_enriched_xml


def _get_llm_fn(provider: str):
    """根据 provider 名称返回对应的 LLM 函数"""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from src.models.llm_providers import (
        gpt5_mini_completion, gpt_completion, gemini_completion
    )
    mapping = {
        "gpt5_mini": gpt5_mini_completion,
        "gpt5": gpt_completion,
        "gemini": gemini_completion,
    }
    fn = mapping.get(provider)
    if fn is None:
        raise ValueError(f"Unknown LLM provider: {provider}. Available: {list(mapping.keys())}")
    return fn


async def _process_single_paper(
    paper_id: str,
    tos_config: dict,
    llm_fn,
    prompt_template: str,
    skip_existing: bool,
    verbose: bool,
) -> Dict:
    if skip_existing and output_exists(paper_id, tos_config):
        if verbose:
            print(f"  [skip] {paper_id}")
        return {"paper_id": paper_id, "status": "skipped"}

    paper_data = await asyncio.to_thread(load_paper_data, paper_id, tos_config)
    if paper_data is None:
        return {"paper_id": paper_id, "status": "failed", "reason": "load error"}

    blocks = extract_conclusion_blocks(paper_data.reasoning_xml)
    if not blocks:
        return {"paper_id": paper_id, "status": "failed", "reason": "no conclusion blocks"}

    tools_by_conclusion = {}
    for block in blocks:
        result = await extract_tools_for_conclusion(
            conclusion_id=block["conclusion_id"],
            conclusion_title=block["conclusion_title"],
            reasoning_xml=block["reasoning_xml"],
            paper_md=paper_data.paper_md,
            prompt_template=prompt_template,
            llm_fn=llm_fn,
        )
        tools_by_conclusion[block["conclusion_id"]] = result

    enriched_xml = enrich_reasoning_xml(paper_data.reasoning_xml, tools_by_conclusion)

    if not validate_enriched_xml(enriched_xml):
        return {"paper_id": paper_id, "status": "failed", "reason": "invalid XML after enrichment"}

    key = await asyncio.to_thread(upload_xml, paper_id, enriched_xml, tos_config)
    if verbose:
        print(f"  [ok] {paper_id} -> {key}")
    return {"paper_id": paper_id, "status": "success", "key": key}


async def run_step2_pipeline_async(config: Dict) -> Dict:
    tos_config = config["tos"]
    llm_config = config["llm"]
    runtime = config["runtime"]

    llm_fn = _get_llm_fn(llm_config["provider"])
    prompt_template = _load_prompt_template(config["prompt"]["template_path"])

    paper_ids = await asyncio.to_thread(
        list_paper_ids, tos_config, runtime.get("sample_limit")
    )
    print(f"\n[Step2] Found {len(paper_ids)} papers")

    semaphore = asyncio.Semaphore(runtime.get("max_workers", 10))

    async def bounded(pid):
        async with semaphore:
            return await _process_single_paper(
                pid, tos_config, llm_fn, prompt_template,
                runtime.get("skip_existing", True),
                runtime.get("verbose", True),
            )

    results = await asyncio.gather(*[bounded(pid) for pid in paper_ids], return_exceptions=False)

    summary = {"total": len(results), "success": 0, "skipped": 0, "failed": 0}
    for r in results:
        summary[r.get("status", "failed")] = summary.get(r.get("status", "failed"), 0) + 1

    print(f"\n[Step2] Done: {summary}")
    return summary


def run_step2_pipeline(config: Dict) -> Dict:
    return asyncio.run(run_step2_pipeline_async(config))


def load_config(config_path: str) -> Dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
