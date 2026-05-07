"""
Step2 主流程 - 加载数据 → LLM 提取工具 → 注入 XML → 上传 TOS
"""

import asyncio
import functools
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from .data_loader import (
    load_paper_data,
    list_paper_ids,
    normalize_paper_id,
    output_exists,
    output_key,
    upload_xml,
)
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


def _save_local_refine_xml(local_dir: str, paper_id: str, xml_text: str) -> None:
    """将 enrich 后的 XML 写入本地，供 Step3 与 selected_chains 对齐读取（与 TOS key 命名一致）。"""
    root = Path(local_dir)
    root.mkdir(parents=True, exist_ok=True)
    name = f"{normalize_paper_id(paper_id)}_reasoning_chain_refine.xml"
    (root / name).write_text(xml_text, encoding="utf-8")


def _tos_one_line(tos_config: dict) -> str:
    bucket = os.getenv("TOS_BUCKET", "").strip() or (tos_config.get("bucket") or "")
    return (
        f"bucket={bucket!r} xml={tos_config.get('xml_source_prefix', '')!r} "
        f"out={tos_config.get('output_prefix', '')!r}"
    )


async def _process_single_paper(
    paper_id: str,
    tos_config: dict,
    llm_fn,
    prompt_template: str,
    skip_existing: bool,
    verbose: bool,
    tos_executor: ThreadPoolExecutor,
    llm_semaphore: asyncio.Semaphore,
    max_conclusions_parallel: int,
    step2_local_output_dir: Optional[str],
) -> Dict:
    loop = asyncio.get_running_loop()

    # 同步 TOS SDK 调用必须进线程池；勿在主线程调用，否则会阻塞整个事件循环、拖垮「并发」。
    if skip_existing:
        exists = await loop.run_in_executor(
            tos_executor,
            functools.partial(output_exists, paper_id, tos_config),
        )
        if exists:
            # if verbose:
            #     print(f"  [skip] {paper_id}", flush=True)
            return {"paper_id": paper_id, "status": "skipped"}

    paper_data = await loop.run_in_executor(
        tos_executor,
        functools.partial(load_paper_data, paper_id, tos_config),
    )
    if paper_data is None:
        return {"paper_id": paper_id, "status": "failed", "reason": "load error"}

    blocks = extract_conclusion_blocks(paper_data.reasoning_xml)
    if not blocks:
        return {"paper_id": paper_id, "status": "failed", "reason": "no conclusion blocks"}

    # 篇内并行度 k：同一时刻本篇最多 k 次 LLM，各次仍占 1 个全局 llm_semaphore 槽。
    # k>1 时峰值槽占用 ≈「活跃论文数×k」，易把全局并发从 max_workers 压到约 max_workers/k。
    k = max(1, min(max_conclusions_parallel, len(blocks)))
    inner = asyncio.Semaphore(k)

    async def _extract_one_block(block: Dict) -> tuple:
        async with inner:
            async with llm_semaphore:
                r = await extract_tools_for_conclusion(
                    conclusion_id=block["conclusion_id"],
                    conclusion_title=block["conclusion_title"],
                    reasoning_xml=block["reasoning_xml"],
                    paper_md=paper_data.paper_md,
                    prompt_template=prompt_template,
                    llm_fn=llm_fn,
                )
        return block["conclusion_id"], r

    raw = await asyncio.gather(*[_extract_one_block(b) for b in blocks], return_exceptions=True)
    tools_by_conclusion: Dict = {}
    for i, item in enumerate(raw):
        if isinstance(item, asyncio.CancelledError):
            raise item
        if isinstance(item, Exception):
            cid = blocks[i]["conclusion_id"]
            return {
                "paper_id": paper_id,
                "status": "failed",
                "reason": f"conclusion {cid}: {item!r}",
            }
        cid, result = item
        tools_by_conclusion[cid] = result

    enriched_xml = enrich_reasoning_xml(paper_data.reasoning_xml, tools_by_conclusion)

    if not validate_enriched_xml(enriched_xml):
        return {"paper_id": paper_id, "status": "failed", "reason": "invalid XML after enrichment"}

    if step2_local_output_dir and str(step2_local_output_dir).strip():
        await loop.run_in_executor(
            tos_executor,
            functools.partial(
                _save_local_refine_xml,
                str(step2_local_output_dir).strip(),
                paper_id,
                enriched_xml,
            ),
        )

    key = await loop.run_in_executor(
        tos_executor,
        functools.partial(upload_xml, paper_id, enriched_xml, tos_config),
    )
    if verbose:
        b = os.getenv("TOS_BUCKET", "").strip() or (tos_config.get("bucket") or "")
        # print(f"  [ok] {paper_id} -> tos://{b}/{key}", flush=True)
    return {"paper_id": paper_id, "status": "success", "key": key}


def _resolve_paper_ids(runtime: dict, tos_config: dict) -> List[str]:
    """
    论文 ID 来源：
    - 若 runtime 含键 paper_ids（如 full_pipeline 注入 Step1 结果），使用该列表（可为空），不做 TOS 全量列举。
    - 若未设置 paper_ids，则调用 list_paper_ids 扫描 xml_source_prefix。
    """
    if "paper_ids" in runtime:
        raw = runtime.get("paper_ids") or []
        ids = [str(x).strip() for x in raw if str(x).strip()]
        lim = runtime.get("sample_limit")
        if lim is not None:
            ids = ids[: int(lim)]
        return ids
    return list_paper_ids(tos_config, runtime.get("sample_limit"))


async def run_step2_pipeline_async(config: Dict) -> Dict:
    tos_config = config["tos"]
    llm_config = config["llm"]
    runtime = config["runtime"]
    debug = bool(runtime.get("debug_step2", False))

    print(f"\n[Step2] TOS: {_tos_one_line(tos_config)}", flush=True)
    tpl_path = config["prompt"]["template_path"]
    print(f"[Step2] prompt 模板: {tpl_path!r}", flush=True)

    print(
        f"[Step2] 正在加载 LLM（provider={llm_config.get('provider')!r}），"
        "若此处卡住多为网络/LiteLLM 初始化…",
        flush=True,
    )
    t_llm = time.perf_counter()
    llm_fn = _get_llm_fn(llm_config["provider"])
    print(f"[Step2] LLM 函数就绪，耗时 {time.perf_counter() - t_llm:.1f}s", flush=True)

    prompt_template = _load_prompt_template(tpl_path)
    print(f"[Step2] prompt 模板已读入，长度 {len(prompt_template)} 字符", flush=True)

    explicit = "paper_ids" in runtime
    t_list = time.perf_counter()
    if explicit:
        src_n = len(runtime.get("paper_ids") or [])
        print(
            f"[Step2] 使用配置中的 paper_ids（源列表 {src_n} 条），不做 TOS 全量列举",
            flush=True,
        )
    else:
        print("[Step2] 未配置 paper_ids，正在 list_objects 扫描 xml 前缀（可能较慢）…", flush=True)

    mw = max(1, int(runtime.get("max_workers", 10)))
    max_conc = max(1, int(runtime.get("max_conclusions_parallel", 1)))
    tos_workers = int(
        runtime.get(
            "tos_thread_workers",
            min(max(mw * 2, 128), 512),
        )
    )
    tos_workers = max(32, min(tos_workers, 1024))

    tos_executor = ThreadPoolExecutor(max_workers=tos_workers, thread_name_prefix="step2_tos")
    llm_semaphore = asyncio.Semaphore(mw)
    loop = asyncio.get_running_loop()

    try:
        paper_ids = await loop.run_in_executor(
            tos_executor,
            functools.partial(_resolve_paper_ids, runtime, tos_config),
        )

        list_dt = time.perf_counter() - t_list
        total = len(paper_ids)
        print(
            f"[Step2] 待处理论文数: {total}（解析耗时 {list_dt:.1f}s，来源="
            f"{'paper_ids' if explicit else 'TOS 列举'}）",
            flush=True,
        )
        print(
            f"[Step2] 并发模型: 全局 LLM 槽={mw}; 单篇 conclusion 并行上限={max_conc} "
            f"(峰值≈min(活跃论文数×{max_conc}, {mw}) 个 LLM 在飞; 设 max_conclusions_parallel=1 时论文级≈{mw} 路); "
            f"TOS 线程池={tos_workers}",
            flush=True,
        )
        if total and debug:
            ex_key = output_key(paper_ids[0], tos_config)
            print(f"[Step2][debug] 示例输出对象键: {ex_key!r}", flush=True)
        if total == 0:
            print("[Step2] Done: no papers", flush=True)
            return {"total": 0, "success": 0, "skipped": 0, "failed": 0}

        _ldir = runtime.get("step2_local_output_dir")
        if _ldir is None:
            _ldir = "data/step2_output"
        step2_local = str(_ldir).strip() or None
        if step2_local:
            print(
                f"[Step2] refine XML 本地镜像: {step2_local}（Step3 与 selected_chains 对齐时使用）",
                flush=True,
            )

        async def bounded(pid: str):
            return await _process_single_paper(
                pid,
                tos_config,
                llm_fn,
                prompt_template,
                runtime.get("skip_existing", True),
                runtime.get("verbose", True),
                tos_executor,
                llm_semaphore,
                max_conc,
                step2_local,
            )

        tasks = [asyncio.create_task(bounded(pid)) for pid in paper_ids]
        print(
            f"  [Step2] 已排队 {total} 篇论文任务，等待首个任务完成…",
            flush=True,
        )
        results: List[Dict] = []
        done = 0
        step = max(1, total // 50)
        for fut in asyncio.as_completed(tasks):
            try:
                r = await fut
            except Exception as e:
                r = {"paper_id": None, "status": "failed", "reason": repr(e)}
            results.append(r)
            if debug and r.get("status") == "failed":
                print(f"  [Step2][debug] failed: {r}", flush=True)
            done += 1
            if done == 1 or done % step == 0 or done == total:
                print(f"  [Step2] progress: {done}/{total} ({100 * done // total}%)", flush=True)

        summary = {"total": len(results), "success": 0, "skipped": 0, "failed": 0}
        for r in results:
            summary[r.get("status", "failed")] = summary.get(r.get("status", "failed"), 0) + 1

        print(f"\n[Step2] Done: {summary}", flush=True)
        return summary
    finally:
        tos_executor.shutdown(wait=True)


def run_step2_pipeline(config: Dict) -> Dict:
    return asyncio.run(run_step2_pipeline_async(config))


def load_config(config_path: str) -> Dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
