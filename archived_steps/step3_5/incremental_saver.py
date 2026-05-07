"""增量输出管理 — 每个 workflow 生成完成后立即写入磁盘"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List

from .schema import GeneratedWorkflow, GenerationStatus


class IncrementalCodeSaver:
    """每成功生成一个 workflow 即落盘，并同步更新索引文件。"""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.workflows_dir = self.output_dir / "workflows"
        self.index_path = self.output_dir / "workflow_index.json"
        self.stats_path = self.output_dir / "generation_stats.json"

        self.index: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    def prepare_fresh_run(self) -> None:
        """清空输出目录，准备新一轮生成。"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.workflows_dir.mkdir(parents=True, exist_ok=True)

        # 清空已有的 workflow 子目录
        for subdir in self.workflows_dir.iterdir():
            if subdir.is_dir():
                for f in subdir.iterdir():
                    f.unlink()
                subdir.rmdir()

        self.index.clear()

    def load_existing_from_disk(self) -> None:
        """从磁盘加载已有的索引（增量模式）。"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.workflows_dir.mkdir(parents=True, exist_ok=True)

        if self.index_path.exists():
            with open(self.index_path, encoding="utf-8") as f:
                self.index = json.load(f)

    async def add_workflow(
        self,
        generated: GeneratedWorkflow,
        verbose: bool = False,
    ) -> None:
        """保存单个 workflow 的 3 个文件，并更新索引。"""
        async with self._lock:
            workflow_id = generated.workflow_id
            workflow_dir = self.workflows_dir / f"workflow_{workflow_id}"
            workflow_dir.mkdir(parents=True, exist_ok=True)

            # 写入 workflow.py
            if generated.workflow_code:
                (workflow_dir / "workflow.py").write_text(
                    generated.workflow_code, encoding="utf-8"
                )

            # 写入 test_example.py
            if generated.test_code:
                (workflow_dir / "test_example.py").write_text(
                    generated.test_code, encoding="utf-8"
                )

            # 写入 metadata.json
            if generated.metadata:
                (workflow_dir / "metadata.json").write_text(
                    json.dumps(generated.metadata, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

            # 更新索引
            self.index[workflow_id] = {
                "dir": str(workflow_dir.relative_to(self.output_dir)),
                "title": generated.title,
                "status": generated.status.value,
                "errors": generated.errors,
            }

            # 立即刷新索引文件
            self._flush_index()

            if verbose:
                print(f"    ✓ Saved {workflow_id} → {workflow_dir.name}", flush=True)

    def _flush_index(self) -> None:
        """写入 workflow_index.json（内部调用，已持锁）。"""
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self.index, f, ensure_ascii=False, indent=2)

    def finalize(self, workflows: List[GeneratedWorkflow]) -> None:
        """生成统计信息文件。"""
        total = len(workflows)
        completed = sum(1 for w in workflows if w.status == GenerationStatus.COMPLETED)
        failed = sum(1 for w in workflows if w.status == GenerationStatus.FAILED)

        stats = {
            "total_workflows": total,
            "completed": completed,
            "failed": failed,
            "success_rate": completed / total if total > 0 else 0.0,
        }

        with open(self.stats_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
