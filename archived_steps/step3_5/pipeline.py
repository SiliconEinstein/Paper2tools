"""Step3.5 主流程 — 将 Step3 的 workflow JSON 转化为可执行代码"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List

import yaml

from .schema import GeneratedWorkflow, GenerationStatus
from .code_generator import WorkflowCodeGenerator
from .test_generator import TestExampleGenerator
from .metadata_generator import WorkflowMetadataGenerator
from .incremental_saver import IncrementalCodeSaver


async def _generate_one_workflow(
    index: int,
    total: int,
    workflow: Dict[str, Any],
    code_gen: WorkflowCodeGenerator,
    test_gen: TestExampleGenerator,
    meta_gen: WorkflowMetadataGenerator,
    semaphore: asyncio.Semaphore,
    saver: IncrementalCodeSaver,
    verbose: bool,
) -> GeneratedWorkflow:
    """生成单个 workflow 的 3 个文件（受信号量控制）。"""
    wf_id = workflow.get("workflow_id", f"unknown_{index}")
    title = workflow.get("title", "")
    result = GeneratedWorkflow(workflow_id=wf_id, title=title)

    async with semaphore:
        if verbose:
            print(f"  [{index}/{total}] Generating {wf_id}...", flush=True)

        # 阶段 1: workflow.py
        try:
            result.workflow_code = await code_gen.generate(workflow)
            result.status = GenerationStatus.CODE_GENERATED
            if verbose:
                print(f"    ✓ workflow.py ({len(result.workflow_code)} chars)", flush=True)
        except Exception as e:
            result.status = GenerationStatus.FAILED
            result.errors.append(f"workflow.py: {e}")
            if verbose:
                print(f"    ✗ workflow.py failed: {e}", flush=True)
            await saver.add_workflow(result, verbose=verbose)
            return result

        # 阶段 2: test_example.py
        try:
            result.test_code = await test_gen.generate(workflow, result.workflow_code)
            result.status = GenerationStatus.TEST_GENERATED
            if verbose:
                print(f"    ✓ test_example.py ({len(result.test_code)} chars)", flush=True)
        except Exception as e:
            result.errors.append(f"test_example.py: {e}")
            if verbose:
                print(f"    ✗ test_example.py failed: {e}", flush=True)
            # 继续生成 metadata，test_code 用空字符串

        # 阶段 3: metadata.json
        try:
            result.metadata = await meta_gen.generate(
                workflow,
                result.workflow_code,
                result.test_code or "",
            )
            if result.status == GenerationStatus.TEST_GENERATED:
                result.status = GenerationStatus.COMPLETED
            if verbose:
                print(f"    ✓ metadata.json", flush=True)
        except Exception as e:
            result.errors.append(f"metadata.json: {e}")
            if verbose:
                print(f"    ✗ metadata.json failed: {e}", flush=True)

        # 即使有部分失败，也保存已有的成果
        if result.status not in (GenerationStatus.COMPLETED, GenerationStatus.FAILED):
            result.status = GenerationStatus.COMPLETED if result.workflow_code else GenerationStatus.FAILED

        await saver.add_workflow(result, verbose=verbose)
        return result


async def _generate_all_workflows(
    workflows: List[Dict[str, Any]],
    code_gen: WorkflowCodeGenerator,
    test_gen: TestExampleGenerator,
    meta_gen: WorkflowMetadataGenerator,
    concurrency: int,
    saver: IncrementalCodeSaver,
    verbose: bool,
) -> List[GeneratedWorkflow]:
    """并发生成所有 workflow。"""
    total = len(workflows)
    semaphore = asyncio.Semaphore(concurrency)

    tasks = [
        asyncio.create_task(
            _generate_one_workflow(
                i, total, wf,
                code_gen, test_gen, meta_gen,
                semaphore, saver, verbose,
            )
        )
        for i, wf in enumerate(workflows, 1)
    ]

    results: List[GeneratedWorkflow] = []
    for fut in asyncio.as_completed(tasks):
        try:
            r = await fut
            results.append(r)
        except Exception as e:
            if verbose:
                print(f"    ✗ Unexpected error: {e}", flush=True)
    return results


async def run_step3_5_pipeline_async(config: Dict[str, Any]) -> List[GeneratedWorkflow]:
    """Step3.5 异步入口。"""
    print("\n" + "=" * 60, flush=True)
    print("Step3.5 Pipeline: Workflow Code Generation", flush=True)
    print("=" * 60, flush=True)

    verbose = config.get("runtime", {}).get("verbose", True)
    concurrency = config.get("runtime", {}).get("concurrency", 5)
    gen_cfg = config.get("generation", {})
    temperature = gen_cfg.get("temperature", 0.3)
    retry_temperature = gen_cfg.get("retry_temperature", 0.1)
    max_retries = gen_cfg.get("max_retries", 1)

    input_path = Path(config["data"]["input_path"])
    output_dir = Path(config["data"]["output_dir"])

    # 1. 加载 Step3 输出
    print("\n[1/3] Loading workflows from Step3...", flush=True)
    with open(input_path, encoding="utf-8") as f:
        workflows = json.load(f)
    print(f"  Loaded {len(workflows)} workflows", flush=True)

    if not workflows:
        print("  No workflows found, exiting.", flush=True)
        return []

    # 2. 初始化
    print("\n[2/3] Initializing generators...", flush=True)
    code_gen = WorkflowCodeGenerator(
        temperature=temperature,
        retry_temperature=retry_temperature,
        max_retries=max_retries,
    )
    test_gen = TestExampleGenerator(
        temperature=temperature,
        retry_temperature=retry_temperature,
        max_retries=max_retries,
    )
    meta_gen = WorkflowMetadataGenerator(
        temperature=temperature,
        retry_temperature=retry_temperature,
        max_retries=max_retries,
    )

    saver = IncrementalCodeSaver(output_dir)
    if config.get("runtime", {}).get("clear_output_dir", False):
        saver.prepare_fresh_run()
        if verbose:
            print(f"  Cleared {output_dir}", flush=True)
    else:
        saver.load_existing_from_disk()
        existing = len(saver.index)
        if verbose and existing > 0:
            print(f"  Found {existing} existing workflows, resuming...", flush=True)

    # 跳过已完成的 workflow（增量）
    completed_ids = {
        wid for wid, entry in saver.index.items()
        if entry.get("status") == "completed"
    }
    pending_workflows = [
        w for w in workflows
        if w.get("workflow_id") not in completed_ids
    ]
    if len(pending_workflows) < len(workflows):
        print(
            f"  Skipping {len(workflows) - len(pending_workflows)} already completed, "
            f"{len(pending_workflows)} to generate",
            flush=True,
        )

    # 3. 生成
    print(f"\n[3/3] Generating code (concurrency={concurrency})...", flush=True)
    results = await _generate_all_workflows(
        pending_workflows,
        code_gen, test_gen, meta_gen,
        concurrency, saver, verbose,
    )

    # 统计
    all_results = results  # 只包含本轮生成的
    completed = sum(1 for r in all_results if r.status == GenerationStatus.COMPLETED)
    failed = sum(1 for r in all_results if r.status == GenerationStatus.FAILED)
    saver.finalize(all_results)

    print("\n" + "=" * 60, flush=True)
    print("Step3.5 Pipeline Complete!", flush=True)
    print(f"  Generated: {completed}, Failed: {failed}, Total: {len(all_results)}", flush=True)
    print(f"  Output: {output_dir}", flush=True)
    print("=" * 60, flush=True)

    return all_results


def run_step3_5_pipeline(config_path: str) -> List[GeneratedWorkflow]:
    """Step3.5 同步入口（从配置文件路径加载）。"""
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return asyncio.run(run_step3_5_pipeline_async(config))
