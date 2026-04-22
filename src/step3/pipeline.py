"""Step3 主流程 - 串联数据加载→workflow 提取→保存"""

import asyncio
import json
from pathlib import Path
from typing import Dict, List

from .data_loader import load_texts
from .workflow_extractor import extract_workflow
from .schema import Workflow


async def _extract_one(
    index: int,
    total: int,
    text: str,
    source_id: str,
    temperature: float,
    semaphore: asyncio.Semaphore,
    verbose: bool,
) -> Workflow | None:
    """提取单个 workflow（受信号量控制）"""
    async with semaphore:
        if verbose:
            print(f"  [{index}/{total}] 提取 {source_id}...")

        workflow = await extract_workflow(
            text=text,
            source_id=source_id,
            temperature=temperature,
        )

        if workflow is not None:
            if verbose:
                print(f"    ✓ {source_id}: {len(workflow.steps)} 个步骤")
        else:
            if verbose:
                print(f"    ✗ {source_id}: 未能提取 workflow")

        return workflow


async def _extract_all(
    texts: list,
    temperature: float,
    concurrency: int,
    verbose: bool,
) -> List[Workflow]:
    """并发提取 workflow"""
    total = len(texts)
    semaphore = asyncio.Semaphore(concurrency)

    tasks = [
        _extract_one(i, total, text, source_id, temperature, semaphore, verbose)
        for i, (text, source_id) in enumerate(texts, 1)
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    workflows = []
    for r in results:
        if isinstance(r, Workflow):
            workflows.append(r)
        elif isinstance(r, Exception):
            if verbose:
                print(f"    ✗ 异常: {r}")

    return workflows


def save_workflows(workflows: List[Workflow], output_dir: Path):
    """保存 workflow 结果到 JSON 文件"""
    output_dir.mkdir(parents=True, exist_ok=True)

    # 保存完整 workflow 库
    library = [w.to_dict() for w in workflows]
    output_path = output_dir / "workflows.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(library, f, ensure_ascii=False, indent=2)

    # 保存统计信息
    stats = {
        "total_workflows": len(workflows),
        "total_steps": sum(len(w.steps) for w in workflows),
        "avg_steps_per_workflow": (
            sum(len(w.steps) for w in workflows) / len(workflows)
            if workflows else 0
        ),
    }
    stats_path = output_dir / "workflow_stats.json"
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def run_step3_pipeline(config: Dict) -> List[Workflow]:
    """
    Step3 主流程入口

    Args:
        config: 配置字典（从 step3_config.yaml 加载）

    Returns:
        提取到的 Workflow 列表
    """
    print("\n" + "=" * 60)
    print("Step3 Pipeline: Workflow Extraction")
    print("=" * 60)

    verbose = config.get("runtime", {}).get("verbose", True)
    temperature = config.get("extraction", {}).get("temperature", 0.3)
    concurrency = config.get("runtime", {}).get("concurrency", 10)
    input_path = Path(config["data"]["input_path"])
    output_dir = Path(config["data"]["output_dir"])

    # 1. 加载文本
    print("\n[1/3] Loading input texts...")
    texts = load_texts(input_path)
    print(f"  ✓ Loaded {len(texts)} text(s)")

    if not texts:
        print("  ✗ No input texts found, exiting.")
        return []

    # 2. 提取 workflow
    print("\n[2/3] Extracting workflows...")
    print(f"  Concurrency: {concurrency}")
    workflows = asyncio.run(_extract_all(texts, temperature, concurrency, verbose))
    print(f"  ✓ Extracted {len(workflows)} workflow(s)")

    # 3. 保存结果
    print("\n[3/3] Saving results...")
    save_workflows(workflows, output_dir)
    print(f"  ✓ Results saved to {output_dir}")

    print("\n" + "=" * 60)
    print("Step3 Pipeline Complete!")
    print(f"  Workflows: {len(workflows)}")
    print(f"  Total steps: {sum(len(w.steps) for w in workflows)}")
    print("=" * 60)

    return workflows
