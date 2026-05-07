"""
从 chain_similarity 产物生成 Markdown + JSON 摘要报告。
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _fmt_sim(x: Any) -> str:
    if x is None:
        return "—"
    try:
        return f"{float(x):.4f}"
    except (TypeError, ValueError):
        return str(x)


def load_chain_similarity_artifacts(
    chain_dir: Path,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """读取 vector_metrics.json、llm_judgments.jsonl、summary.json（summary 可选）。"""
    chain_dir = Path(chain_dir)
    vec_path = chain_dir / "vector_metrics.json"
    llm_path = chain_dir / "llm_judgments.jsonl"
    sum_path = chain_dir / "summary.json"

    if not vec_path.is_file():
        raise FileNotFoundError(f"缺少 {vec_path}")

    with open(vec_path, encoding="utf-8") as f:
        vector_records = json.load(f)
    if not isinstance(vector_records, list):
        raise ValueError("vector_metrics.json 顶层应为数组")

    llm_rows: List[Dict[str, Any]] = []
    if llm_path.is_file():
        with open(llm_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                llm_rows.append(json.loads(line))

    run_summary: Dict[str, Any] = {}
    if sum_path.is_file():
        with open(sum_path, encoding="utf-8") as f:
            run_summary = json.load(f)

    return vector_records, llm_rows, run_summary


def _aggregate_vector_stats(vector_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    means: List[float] = []
    medians: List[float] = []
    mins_l: List[float] = []
    maxs_l: List[float] = []
    n_missing_any = 0
    n_no_pairs = 0

    for rec in vector_records:
        pc = rec.get("pairwise_cosine") or {}
        miss = rec.get("missing_vector_chain_ids") or []
        if miss:
            n_missing_any += 1
        m = pc.get("mean")
        if m is None:
            n_no_pairs += 1
            continue
        means.append(float(m))
        if pc.get("median") is not None:
            medians.append(float(pc["median"]))
        if pc.get("min") is not None:
            mins_l.append(float(pc["min"]))
        if pc.get("max") is not None:
            maxs_l.append(float(pc["max"]))

    def _avg(xs: List[float]) -> Optional[float]:
        return float(sum(xs) / len(xs)) if xs else None

    return {
        "n_clusters": len(vector_records),
        "n_clusters_with_missing_vectors": n_missing_any,
        "n_clusters_no_pairwise": n_no_pairs,
        "across_clusters_mean_of_pairwise_mean": _avg(means),
        "across_clusters_mean_of_pairwise_median": _avg(medians),
        "across_clusters_min_of_pairwise_min": min(mins_l) if mins_l else None,
        "across_clusters_max_of_pairwise_max": max(maxs_l) if maxs_l else None,
    }


def _aggregate_llm_stats(llm_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    ok = [r for r in llm_rows if "error" not in r]
    err = [r for r in llm_rows if "error" in r]

    def _count_field(field: str) -> Dict[str, int]:
        c: Counter[str] = Counter()
        for r in ok:
            v = r.get(field)
            if v is None:
                c["(空)"] += 1
            else:
                c[str(v).strip().lower()] += 1
        return dict(c)

    return {
        "n_llm_rows": len(llm_rows),
        "n_llm_ok": len(ok),
        "n_llm_error": len(err),
        "research_question_alignment": _count_field("research_question_alignment"),
        "reasoning_path_similarity": _count_field("reasoning_path_similarity"),
        "overall_chain_similarity": _count_field("overall_chain_similarity"),
        "confidence": _count_field("confidence"),
    }


def build_chain_similarity_report_bundle(
    vector_records: List[Dict[str, Any]],
    llm_rows: List[Dict[str, Any]],
    run_summary: Dict[str, Any],
) -> Tuple[str, Dict[str, Any]]:
    """返回 (markdown, json_summary)。"""
    v_agg = _aggregate_vector_stats(vector_records)
    l_agg = _aggregate_llm_stats(llm_rows)

    llm_by_cluster: Dict[int, Dict[str, Any]] = {}
    for r in llm_rows:
        cid = r.get("cluster_id")
        if cid is not None:
            try:
                llm_by_cluster[int(cid)] = r
            except (TypeError, ValueError):
                pass

    lines: List[str] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append("# 思维链相似度评估报告")
    lines.append("")
    lines.append(f"生成时间: {now}")
    lines.append("")

    if run_summary:
        lines.append("## 运行摘要")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(run_summary, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")

    lines.append("## 向量相似度（簇内两两余弦）汇总")
    lines.append("")
    lines.append("| 指标 | 值 |")
    lines.append("|------|-----|")
    lines.append(f"| 簇数量 | {v_agg['n_clusters']} |")
    lines.append(f"| 存在缺失向量的簇数 | {v_agg['n_clusters_with_missing_vectors']} |")
    lines.append(f"| 无有效两两对的簇数（<2 条有效向量） | {v_agg['n_clusters_no_pairwise']} |")
    lines.append(
        f"| 各簇 pairwise **mean** 的全局平均 | {_fmt_sim(v_agg['across_clusters_mean_of_pairwise_mean'])} |"
    )
    lines.append(
        f"| 各簇 pairwise **median** 的全局平均 | {_fmt_sim(v_agg['across_clusters_mean_of_pairwise_median'])} |"
    )
    lines.append(
        f"| 所有簇中 pairwise **min** 的最小值 | {_fmt_sim(v_agg['across_clusters_min_of_pairwise_min'])} |"
    )
    lines.append(
        f"| 所有簇中 pairwise **max** 的最大值 | {_fmt_sim(v_agg['across_clusters_max_of_pairwise_max'])} |"
    )
    lines.append("")

    lines.append("## LLM 判断分布（有效条数）")
    lines.append("")
    lines.append(f"- 总行数: {l_agg['n_llm_rows']}；成功: {l_agg['n_llm_ok']}；失败: {l_agg['n_llm_error']}")
    lines.append("")

    def _dump_counts(title: str, d: Dict[str, int]) -> None:
        lines.append(f"### {title}")
        lines.append("")
        if not d:
            lines.append("（无数据）")
        else:
            for k, v in sorted(d.items(), key=lambda x: (-x[1], x[0])):
                lines.append(f"- `{k}`: {v}")
        lines.append("")

    _dump_counts("研究问题一致性 (research_question_alignment)", l_agg["research_question_alignment"])
    _dump_counts("推理链路相似性 (reasoning_path_similarity)", l_agg["reasoning_path_similarity"])
    _dump_counts("整体相似度 (overall_chain_similarity)", l_agg["overall_chain_similarity"])
    _dump_counts("置信度 (confidence)", l_agg["confidence"])

    lines.append("## 逐簇明细")
    lines.append("")
    lines.append(
        "| cluster_id | 选中链数 | 有向量数 | pairwise mean | median | min | max | "
        "LLM 问题一致 | LLM 推理相似 | LLM 整体 | 置信度 |"
    )
    lines.append("|------------|----------|----------|---------------|--------|-----|-----|--------------|--------------|---------|--------|")

    for rec in sorted(vector_records, key=lambda r: r.get("cluster_id", -10**9)):
        cid = rec.get("cluster_id")
        pc = rec.get("pairwise_cosine") or {}
        lr = llm_by_cluster.get(int(cid)) if cid is not None else None

        def _lc(key: str) -> str:
            if not lr or "error" in lr:
                return "—"
            v = lr.get(key)
            return str(v) if v is not None else "—"

        lines.append(
            f"| {cid} | {rec.get('n_chains_in_selection', '—')} | "
            f"{rec.get('n_chains_with_vector', '—')} | "
            f"{_fmt_sim(pc.get('mean'))} | {_fmt_sim(pc.get('median'))} | "
            f"{_fmt_sim(pc.get('min'))} | {_fmt_sim(pc.get('max'))} | "
            f"{_lc('research_question_alignment')} | {_lc('reasoning_path_similarity')} | "
            f"{_lc('overall_chain_similarity')} | {_lc('confidence')} |"
        )

    lines.append("")
    lines.append("## LLM 理由摘录（每簇首句，完整见 llm_judgments.jsonl）")
    lines.append("")

    for r in sorted(llm_rows, key=lambda x: x.get("cluster_id", -10**9)):
        cid = r.get("cluster_id", "?")
        if "error" in r:
            lines.append(f"- **cluster {cid}**（解析失败）: `{r.get('error', '')[:200]}`")
            continue
        rat = (r.get("rationale_zh") or "").strip().replace("\n", " ")
        if len(rat) > 280:
            rat = rat[:280] + "…"
        lines.append(f"- **cluster {cid}**: {rat or '（无理由字段）'}")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*本报告由 `run_chain_similarity_eval_report.py` 根据 `chain_similarity/` 下 JSON 产物自动生成。*")

    json_summary: Dict[str, Any] = {
        "generated_at_utc": now,
        "vector_aggregate": v_agg,
        "llm_aggregate": l_agg,
        "run_summary": run_summary or None,
    }

    return "\n".join(lines), json_summary


def write_chain_similarity_reports(
    chain_dir: Path,
    step4_output: Path,
    *,
    md_name: str = "chain_similarity_report.md",
    json_name: str = "chain_similarity_report.summary.json",
) -> Tuple[Path, Path]:
    """从 chain_dir 读产物，写入 step4_output 下 md + json。"""
    vec, llm, summ = load_chain_similarity_artifacts(chain_dir)
    md_text, json_summary = build_chain_similarity_report_bundle(vec, llm, summ)

    step4_output = Path(step4_output)
    step4_output.mkdir(parents=True, exist_ok=True)
    md_path = step4_output / md_name
    js_path = step4_output / json_name
    md_path.write_text(md_text, encoding="utf-8")
    with open(js_path, "w", encoding="utf-8") as f:
        json.dump(json_summary, f, ensure_ascii=False, indent=2)
    return md_path, js_path
