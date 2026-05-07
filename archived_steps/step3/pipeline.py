"""Step3 主流程 - 串联数据加载→workflow 提取→保存"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .data_loader import WorkflowLoadItem, load_texts
from .workflow_extractor import extract_workflow
from .schema import Workflow


def resolve_step3_tos_enrich_config(data_cfg: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    selected_chains 模式下从 TOS 拉 Step2 refine 时，返回与 ``src.step2.data_loader`` 兼容的 tos dict。
    需要 ``output_prefix``（及凭证：环境变量或 YAML 中的 bucket/endpoint 等）。
    """
    if not isinstance(data_cfg, dict) or not data_cfg.get("step2_enrich_from_tos"):
        return None
    tos_cfg = data_cfg.get("tos")
    if not isinstance(tos_cfg, dict) or not str(tos_cfg.get("output_prefix") or "").strip():
        scp = data_cfg.get("step2_config_path")
        if scp:
            p = Path(scp)
            if not p.is_file():
                raise FileNotFoundError(f"step2_config_path 不存在: {p.resolve()}")
            with open(p, encoding="utf-8") as f:
                s2 = yaml.safe_load(f) or {}
            tos_cfg = s2.get("tos")
    if not isinstance(tos_cfg, dict) or not str(tos_cfg.get("output_prefix") or "").strip():
        raise ValueError(
            "step2_enrich_from_tos=true 需要 data.tos.output_prefix，"
            "或设置 data.step2_config_path 指向含 tos.output_prefix 的 Step2 配置。"
        )
    return dict(tos_cfg)


def _merge_member_paper_ids(workflow: Workflow, provenance: Optional[Dict]) -> None:
    """将簇内成员 paper_id 并入 source_ids，便于溯源。"""
    if not provenance or workflow is None:
        return
    members = provenance.get("members")
    if not isinstance(members, list):
        return
    for m in members:
        if not isinstance(m, dict):
            continue
        pid = m.get("paper_id")
        if pid and pid not in workflow.source_ids:
            workflow.source_ids.append(pid)


async def _extract_one(
    index: int,
    total: int,
    item: WorkflowLoadItem,
    temperature: float,
    semaphore: asyncio.Semaphore,
    verbose: bool,
) -> Workflow | None:
    """提取单个 workflow（受信号量控制）"""
    async with semaphore:
        if verbose:
            print(f"  [{index}/{total}] 提取 {item.source_id}...", flush=True)

        workflow = await extract_workflow(
            text=item.text,
            source_id=item.source_id,
            temperature=temperature,
        )

        if workflow is not None:
            if item.provenance:
                workflow.provenance = dict(item.provenance)
            _merge_member_paper_ids(workflow, item.provenance)
            if verbose:
                print(f"    ✓ {item.source_id}: {len(workflow.steps)} 个步骤", flush=True)
        else:
            if verbose:
                print(f"    ✗ {item.source_id}: 未能提取 workflow", flush=True)

        return workflow


async def _extract_all_incremental(
    items: List[WorkflowLoadItem],
    temperature: float,
    concurrency: int,
    verbose: bool,
    saver: _IncrementalWorkflowSaver,
) -> List[Workflow]:
    """并发提取 workflow，每成功一个立即由 saver 落盘。"""
    total = len(items)
    semaphore = asyncio.Semaphore(concurrency)

    async def _run_one(i: int, item: WorkflowLoadItem) -> Workflow | None:
        w = await _extract_one(i, total, item, temperature, semaphore, verbose)
        if w is not None:
            await saver.add_workflow(w, verbose=verbose)
        return w

    tasks = [
        asyncio.create_task(_run_one(i, item))
        for i, item in enumerate(items, 1)
    ]
    workflows: List[Workflow] = []
    for fut in asyncio.as_completed(tasks):
        try:
            w = await fut
        except Exception as e:
            if verbose:
                print(f"    ✗ 异常: {e}", flush=True)
            continue
        if isinstance(w, Workflow):
            workflows.append(w)
    return workflows


def _workflow_file_stem(w: Workflow) -> str:
    """单文件 JSON 文件名（不含扩展名），优先与簇 id 对齐。"""
    prov = w.provenance or {}
    if "cluster_id" in prov:
        try:
            return f"cluster_{int(prov['cluster_id'])}"
        except (TypeError, ValueError):
            pass
    raw = (w.workflow_id or "workflow").strip() or "workflow"
    safe = re.sub(r"[^0-9A-Za-z._-]+", "_", raw).strip("._") or "workflow"
    return safe[:180]


class _IncrementalWorkflowSaver:
    """每成功提取一个 workflow 即落盘，并同步更新汇总 JSON（线程安全的协程锁）。"""

    def __init__(self, output_dir: Path, cluster_base_dir: Optional[Path] = None):
        self.output_dir = Path(output_dir)
        self.per_dir = self.output_dir / "workflows"
        self.cluster_base_dir = Path(cluster_base_dir) if cluster_base_dir else None
        self.library: List[Dict] = []
        self.index_rows: List[Dict[str, str]] = []
        self.used: set[str] = set()
        self._lock = asyncio.Lock()

    def prepare_fresh_run(self) -> None:
        """清空子目录内单文件并重置内存状态（新一轮完整抽取）。"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.per_dir.mkdir(parents=True, exist_ok=True)
        for old in self.per_dir.glob("*.json"):
            try:
                old.unlink()
            except OSError:
                pass
        self.library.clear()
        self.index_rows.clear()
        self.used.clear()

    def load_existing_from_disk(self) -> None:
        """不清空目录时，把已有单文件读入内存以便继续追加并刷新汇总。"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.per_dir.mkdir(parents=True, exist_ok=True)
        self.library.clear()
        self.index_rows.clear()
        self.used.clear()
        for p in sorted(self.per_dir.glob("*.json")):
            try:
                with open(p, encoding="utf-8") as f:
                    d = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(d, dict):
                continue
            self.used.add(p.stem)
            rel = f"workflows/{p.name}"
            self.library.append(d)
            self.index_rows.append(
                {
                    "file": rel,
                    "workflow_id": str(d.get("workflow_id", "")),
                    "title": str(d.get("title", "")),
                }
            )
        self._rewrite_aggregates()

    def _rewrite_aggregates(self) -> None:
        with open(self.output_dir / "workflows.json", "w", encoding="utf-8") as f:
            json.dump(self.library, f, ensure_ascii=False, indent=2)
        with open(self.output_dir / "workflows_index.json", "w", encoding="utf-8") as f:
            json.dump(self.index_rows, f, ensure_ascii=False, indent=2)
        n = len(self.library)
        total_steps = sum(
            len(d.get("steps") or []) for d in self.library if isinstance(d, dict)
        )
        stats = {
            "total_workflows": n,
            "total_steps": total_steps,
            "avg_steps_per_workflow": (total_steps / n if n else 0),
            "per_workflow_dir": "workflows",
        }
        with open(self.output_dir / "workflow_stats.json", "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)

    async def add_workflow(self, w: Workflow, *, verbose: bool) -> str:
        async with self._lock:
            stem = _workflow_file_stem(w)
            name = stem
            n = 0
            while name in self.used:
                n += 1
                name = f"{stem}_{n}"
            self.used.add(name)
            rel = f"workflows/{name}.json"
            path = self.per_dir / f"{name}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(w.to_dict(), f, ensure_ascii=False, indent=2)
            self.library.append(w.to_dict())
            self.index_rows.append(
                {"file": rel, "workflow_id": w.workflow_id, "title": w.title}
            )
            self._rewrite_aggregates()
            if verbose:
                print(f"    [saved] {rel}", flush=True)

            # 如果配置了 cluster_base_dir，同时保存到对应的 cluster 文件夹
            if self.cluster_base_dir:
                cluster_id = w.provenance.get("cluster_id") if w.provenance else None
                if cluster_id is not None:
                    cluster_dir = self.cluster_base_dir / f"cluster_{cluster_id}"
                    cluster_dir.mkdir(parents=True, exist_ok=True)
                    cluster_workflow_path = cluster_dir / "workflow.json"
                    with open(cluster_workflow_path, "w", encoding="utf-8") as f:
                        json.dump(w.to_dict(), f, ensure_ascii=False, indent=2)
                    if verbose:
                        print(f"    [saved to cluster] cluster_{cluster_id}/workflow.json", flush=True)

            return rel


def save_workflows(workflows: List[Workflow], output_dir: Path):
    """
    保存 workflow：每个工作流单独 ``workflows/<stem>.json``，并写汇总 ``workflows.json`` 与 ``workflow_stats.json``。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    per_dir = output_dir / "workflows"
    per_dir.mkdir(parents=True, exist_ok=True)

    for old in per_dir.glob("*.json"):
        try:
            old.unlink()
        except OSError:
            pass

    used: set[str] = set()
    index_rows: List[Dict[str, str]] = []
    for w in workflows:
        stem = _workflow_file_stem(w)
        name = stem
        n = 0
        while name in used:
            n += 1
            name = f"{stem}_{n}"
        used.add(name)
        rel = f"workflows/{name}.json"
        index_rows.append({"file": rel, "workflow_id": w.workflow_id, "title": w.title})
        with open(per_dir / f"{name}.json", "w", encoding="utf-8") as f:
            json.dump(w.to_dict(), f, ensure_ascii=False, indent=2)

    library = [w.to_dict() for w in workflows]
    with open(output_dir / "workflows.json", "w", encoding="utf-8") as f:
        json.dump(library, f, ensure_ascii=False, indent=2)

    with open(output_dir / "workflows_index.json", "w", encoding="utf-8") as f:
        json.dump(index_rows, f, ensure_ascii=False, indent=2)

    stats = {
        "total_workflows": len(workflows),
        "total_steps": sum(len(w.steps) for w in workflows),
        "avg_steps_per_workflow": (
            sum(len(w.steps) for w in workflows) / len(workflows)
            if workflows else 0
        ),
        "per_workflow_dir": "workflows",
    }
    with open(output_dir / "workflow_stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


async def run_step3_pipeline_async(config: Dict) -> List[Workflow]:
    """
    Step3 异步入口：供已在 asyncio 事件循环内的调用方使用（如 run_full_pipeline.main）。
    """
    print("\n" + "=" * 60, flush=True)
    print("Step3 Pipeline: Workflow Extraction", flush=True)
    print("=" * 60, flush=True)

    verbose = config.get("runtime", {}).get("verbose", True)
    temperature = config.get("extraction", {}).get("temperature", 0.3)
    concurrency = config.get("runtime", {}).get("concurrency", 10)
    input_path = Path(config["data"]["input_path"])
    output_dir = Path(config["data"]["output_dir"])
    data_cfg = config.get("data") or {}
    step2_dir_raw = data_cfg.get("step2_enriched_dir")
    step2_enriched_dir = Path(step2_dir_raw) if step2_dir_raw else None
    step2_enrich_tos = resolve_step3_tos_enrich_config(data_cfg)

    # 1. 加载文本
    print("\n[1/3] Loading input texts...", flush=True)
    if step2_enrich_tos:
        bkt = os.getenv("TOS_BUCKET", "").strip() or str(
            step2_enrich_tos.get("bucket") or ""
        ).strip()
        pref = str(step2_enrich_tos.get("output_prefix") or "").strip().strip("/")
        print(
            f"  Step2 enrich: TOS tos://{bkt}/{pref}/（与 selected_chains 联用；失败回退本地/chain_text）",
            flush=True,
        )
    elif step2_enriched_dir:
        print(
            f"  Step2 enrich 本地目录: {step2_enriched_dir}（与 selected_chains 联用）",
            flush=True,
        )
    items = load_texts(
        input_path,
        step2_enriched_dir=step2_enriched_dir,
        step2_enrich_tos=step2_enrich_tos,
    )
    print(f"  ✓ Loaded {len(items)} input(s) (each → one workflow extraction)", flush=True)

    if not items:
        print("  ✗ No input texts found, exiting.", flush=True)
        return []

    # 2. 提取并增量保存（每完成一个即写入 workflows/<stem>.json 并刷新汇总）
    print("\n[2/3] Extracting workflows (incremental save)...", flush=True)
    print(f"  Concurrency: {concurrency}", flush=True)

    # 如果配置了 workflows_base_dir，则同时保存到 cluster 文件夹
    cluster_base_dir = None
    workflows_base_raw = data_cfg.get("workflows_base_dir")
    if workflows_base_raw:
        cluster_base_dir = Path(workflows_base_raw)
        if verbose:
            print(f"  将同时保存 workflow 到 cluster 文件夹: {cluster_base_dir}", flush=True)

    saver = _IncrementalWorkflowSaver(output_dir, cluster_base_dir=cluster_base_dir)
    if config.get("runtime", {}).get("clear_workflows_dir", True):
        saver.prepare_fresh_run()
        if verbose:
            print(f"  已清空 {output_dir / 'workflows'}/*.json，开始本轮抽取", flush=True)
    else:
        saver.load_existing_from_disk()
        if verbose:
            print(
                f"  保留已有 {len(saver.library)} 个单文件，继续增量写入 {output_dir / 'workflows'}",
                flush=True,
            )

    workflows = await _extract_all_incremental(
        items, temperature, concurrency, verbose, saver
    )
    print(f"  ✓ 本轮成功提取 {len(workflows)} 个 workflow(s)", flush=True)

    # 3. 汇总已在增量保存中更新；无额外批量写盘
    print("\n[3/3] Output finalized (incremental)", flush=True)
    print(f"  ✓ 目录: {output_dir}", flush=True)

    print("\n" + "=" * 60, flush=True)
    print("Step3 Pipeline Complete!", flush=True)
    print(f"  Workflows: {len(workflows)}", flush=True)
    print(f"  Total steps: {sum(len(w.steps) for w in workflows)}", flush=True)
    print("=" * 60, flush=True)

    return workflows


def run_step3_pipeline(config: Dict) -> List[Workflow]:
    """
    Step3 同步入口：脚本 / CLI 在无运行中事件循环时使用。
    """
    return asyncio.run(run_step3_pipeline_async(config))
