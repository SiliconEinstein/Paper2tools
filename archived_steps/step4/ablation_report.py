"""
Step4 消融：baseline vs variant workflow 对齐比较结果 → Markdown + JSON 摘要。
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.is_file():
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _pct(num: int, den: int) -> str:
    if den <= 0:
        return "—"
    return f"{100.0 * num / den:.1f}%"


def _arm_section(
    arm_key: str,
    summary: Dict[str, Any],
    rows: List[Dict[str, Any]],
    *,
    table_row_limit: int = 100,
) -> List[str]:
    lines: List[str] = []
    lines.append(f"## 对比臂: `{arm_key}`")
    lines.append("")

    if summary.get("skipped"):
        lines.append("（该臂未执行或跳过：无对齐簇）")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(summary, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
        return lines

    n_ok = int(summary.get("n_comparisons_ok") or 0)
    n_fail = int(summary.get("n_comparisons_failed") or 0)
    bw = int(summary.get("baseline_wins") or 0)
    vw = int(summary.get("variant_wins") or 0)
    ties = int(summary.get("ties") or 0)
    denom = max(1, n_ok)

    lines.append("### 汇总")
    lines.append("")
    lines.append("| 指标 | 数值 | 占比（相对有效比较） |")
    lines.append("|------|------|----------------------|")
    lines.append(f"| 对齐簇数（请求比较数） | {summary.get('n_aligned', '—')} | — |")
    lines.append(f"| 有效 LLM 比较 | {n_ok} | 100% |")
    lines.append(f"| 失败 | {n_fail} | — |")
    lines.append(f"| **baseline 胜** (better=A) | {bw} | {_pct(bw, denom)} |")
    lines.append(f"| **variant 胜** (better=B) | {vw} | {_pct(vw, denom)} |")
    lines.append(f"| 平局 (tie) | {ties} | {_pct(ties, denom)} |")
    lines.append("")
    lines.append(
        f"- baseline: `{summary.get('baseline_root', '')}` （标签 `{summary.get('baseline_tag', '')}`）\n"
        f"- variant: `{summary.get('variant_root', '')}` （标签 `{summary.get('variant_tag', '')}`）"
    )
    lines.append("")

    only_b = summary.get("only_baseline_cluster_ids") or []
    only_v = summary.get("only_variant_cluster_ids") or []
    if only_b:
        lines.append(f"- 仅 baseline 有簇（前 20 个 id）: {only_b[:20]}{'…' if len(only_b) > 20 else ''}")
    if only_v:
        lines.append(f"- 仅 variant 有簇（前 20 个 id）: {only_v[:20]}{'…' if len(only_v) > 20 else ''}")
    if only_b or only_v:
        lines.append("")

    ok_rows = [r for r in rows if "error" not in r]
    conf_c: Counter[str] = Counter()
    for r in ok_rows:
        c = r.get("confidence")
        conf_c[str(c).strip() if c is not None else "(空)"] += 1
    if conf_c:
        lines.append("### LLM confidence 分布（有效比较）")
        lines.append("")
        for k, v in conf_c.most_common():
            lines.append(f"- `{k}`: {v}")
        lines.append("")

    lines.append("### 逐簇结果（节选）")
    lines.append("")
    ok_sorted = sorted(ok_rows, key=lambda r: r.get("cluster_id", 0))
    hidden = 0
    if len(ok_sorted) > table_row_limit:
        hidden = len(ok_sorted) - table_row_limit
        ok_sorted = ok_sorted[:table_row_limit]

    lines.append("| cluster_id | better | confidence | reason（截断） |")
    lines.append("|------------|--------|------------|----------------|")
    for r in ok_sorted:
        cid = r.get("cluster_id", "—")
        b = r.get("better", "—")
        conf = r.get("confidence", "—")
        reason = (r.get("reason") or "").replace("\n", " ").strip()
        if len(reason) > 160:
            reason = reason[:160] + "…"
        lines.append(f"| {cid} | {b} | {conf} | {reason or '—'} |")
    if hidden:
        lines.append("")
        lines.append(f"*另有 {hidden} 条有效比较未展示；完整列表见本目录 `comparisons.jsonl`。*")
    lines.append("")

    err_rows = [r for r in rows if "error" in r]
    if err_rows:
        lines.append("### 解析/调用失败（节选）")
        lines.append("")
        for r in err_rows[:15]:
            lines.append(f"- cluster {r.get('cluster_id', '?')}: `{str(r.get('error', ''))[:200]}`")
        if len(err_rows) > 15:
            lines.append(f"- … 共 {len(err_rows)} 条失败")
        lines.append("")

    return lines


def build_ablation_report_markdown(
    output_dir: Path,
    aggregate: Dict[str, Any],
    *,
    table_row_limit: int = 100,
) -> Tuple[str, Dict[str, Any]]:
    """根据 output_dir 下 aggregate_summary.json 与各子目录生成报告正文与结构化摘要。"""
    output_dir = Path(output_dir)
    lines: List[str] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append("# Workflow 消融对比评估报告（Step4 对齐比较）")
    lines.append("")
    lines.append(f"生成时间: {now}")
    lines.append("")
    lines.append("> better=`A` 表示 **baseline** 工作流更好；better=`B` 表示 **variant** 更好；`tie` 为平局。")
    lines.append("")

    lines.append("## 实验配置")
    lines.append("")
    lines.append(f"- **baseline 目录**: `{aggregate.get('baseline_dir', '')}`")
    v5 = aggregate.get("variant_5_dir")
    v1 = aggregate.get("variant_1_dir")
    if v5:
        lines.append(f"- **variant（5 条/簇）**: `{v5}`")
    if v1:
        lines.append(f"- **variant（1 条/簇）**: `{v1}`")
    lines.append(f"- **结果根目录**: `{output_dir.resolve()}`")
    lines.append("")

    json_summary: Dict[str, Any] = {
        "generated_at_utc": now,
        "baseline_dir": aggregate.get("baseline_dir"),
        "variant_5_dir": aggregate.get("variant_5_dir"),
        "variant_1_dir": aggregate.get("variant_1_dir"),
        "arms": {},
    }

    comparisons = aggregate.get("comparisons") or {}
    for arm_key in ("10_vs_5", "10_vs_1"):
        if arm_key not in comparisons:
            continue
        sub = output_dir / arm_key
        summ_path = sub / "summary.json"
        jl_path = sub / "comparisons.jsonl"
        summary = comparisons[arm_key]
        if summ_path.is_file():
            try:
                with open(summ_path, encoding="utf-8") as f:
                    summary = json.load(f)
            except Exception:
                pass
        rows = _read_jsonl(jl_path)
        lines.extend(_arm_section(arm_key, summary, rows, table_row_limit=table_row_limit))
        json_summary["arms"][arm_key] = {
            "summary": summary,
            "n_jsonl_rows": len(rows),
            "n_ok": sum(1 for r in rows if "error" not in r),
        }

    if not json_summary["arms"]:
        lines.append("## 无对比臂数据")
        lines.append("")
        lines.append("`aggregate_summary.json` 中 `comparisons` 为空或缺少 10_vs_5 / 10_vs_1。")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*由 `src/step4/ablation_report.py` 根据消融脚本产出自动生成。*")

    return "\n".join(lines), json_summary


def write_ablation_report(
    output_dir: Path,
    *,
    table_row_limit: int = 100,
) -> Tuple[Path, Path]:
    """读取 `output_dir/aggregate_summary.json`，写入 `ablation_report.md` 与 `ablation_report.summary.json`。"""
    output_dir = Path(output_dir)
    agg_path = output_dir / "aggregate_summary.json"
    if not agg_path.is_file():
        raise FileNotFoundError(f"缺少 {agg_path}，请先运行消融对比脚本")

    with open(agg_path, encoding="utf-8") as f:
        aggregate = json.load(f)

    md_text, js = build_ablation_report_markdown(
        output_dir, aggregate, table_row_limit=table_row_limit
    )
    md_out = output_dir / "ablation_report.md"
    js_out = output_dir / "ablation_report.summary.json"
    md_out.write_text(md_text, encoding="utf-8")
    with open(js_out, "w", encoding="utf-8") as f:
        json.dump(js, f, ensure_ascii=False, indent=2)
    return md_out, js_out
