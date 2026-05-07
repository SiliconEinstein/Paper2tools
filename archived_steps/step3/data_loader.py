"""数据加载模块 - 加载任意文本文件"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .selected_chains_loader import try_build_cluster_inputs_from_json
from .step2_loader import load_texts_from_step2_output


@dataclass
class WorkflowLoadItem:
    """单条 Step3 提取任务的输入。"""

    text: str
    source_id: str
    provenance: Optional[Dict[str, Any]] = None


def load_text(path: Path) -> Tuple[str, str]:
    """
    加载单个文本文件

    Args:
        path: 文件路径

    Returns:
        (text, source_id) 元组
    """
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    if not path.is_file():
        raise ValueError(f"路径不是文件: {path}")

    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    source_id = path.stem
    return text, source_id


def load_texts(
    path: Path,
    mode: str = "auto",
    step2_enriched_dir: Optional[Path] = None,
    step2_enrich_tos: Optional[Dict[str, Any]] = None,
) -> List[WorkflowLoadItem]:
    """
    加载 Step3 所需的输入列表（每项一次 workflow 提取）。

    Args:
        path: 文件或目录路径
        mode: 加载模式
            - "auto": 自动检测（默认）。若为 Step1 的 selected_chains.json（数组且含 cluster_id），则按簇拆分。
            - "step2_output": 从 Step2 输出的 XML 文件加载
            - "raw": 不做 selected_chains 检测；单文件整段、目录按扩展名枚举
        step2_enriched_dir: 含 ``*_reasoning_chain_refine.xml`` 的本地目录。与 selected_chains.json
            联用时作 TOS 失败后的回退，或单独使用（未配 TOS 时）。
        step2_enrich_tos: 与 Step2 相同的 ``tos`` dict（至少 ``output_prefix``）。与 selected_chains
            联用时优先从 TOS 按 ``output_key(paper_id)`` 下载 refine XML。

    Returns:
        WorkflowLoadItem 列表
    """
    path = Path(path)
    step2_dir = Path(step2_enriched_dir) if step2_enriched_dir else None

    if mode == "step2_output" or (
        mode == "auto" and path.is_dir() and any(path.glob("*_reasoning_chain_refine.xml"))
    ):
        pairs = load_texts_from_step2_output(path)
        return [WorkflowLoadItem(text=t, source_id=s) for t, s in pairs]

    if path.is_file() and path.suffix.lower() == ".json" and mode == "auto":
        clustered = try_build_cluster_inputs_from_json(
            path, step2_dir, step2_enrich_tos
        )
        if clustered is not None:
            return [
                WorkflowLoadItem(text=t, source_id=s, provenance=p)
                for t, s, p in clustered
            ]

    if path.is_file():
        text, source_id = load_text(path)
        return [WorkflowLoadItem(text=text, source_id=source_id)]

    if not path.is_dir():
        raise ValueError(f"路径既不是文件也不是目录: {path}")

    supported_extensions = {".txt", ".xml", ".json", ".md"}
    results: List[WorkflowLoadItem] = []

    for file_path in sorted(path.iterdir()):
        if file_path.is_file() and file_path.suffix in supported_extensions:
            try:
                text, source_id = load_text(file_path)
                results.append(WorkflowLoadItem(text=text, source_id=source_id))
            except Exception as e:
                print(f"  ✗ 加载文件失败 {file_path.name}: {e}")

    return results
