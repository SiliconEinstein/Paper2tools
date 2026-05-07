"""
Step4：从 Step3 加载 workflow，成对采样后由 LLM 评判优劣，输出结果与排名。
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from .llm_fn import get_completion_fn


def _load_prompt_template(template_path: str) -> str:
    path = Path(template_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / template_path
    return path.read_text(encoding="utf-8")


def _parse_compare_response(text: str) -> Dict[str, Any]:
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", s)
        if m:
            return json.loads(m.group())
        raise


def load_workflow_entries(workflows_root: Path) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Returns [(relative_id, workflow_dict), ...].
    relative_id 用于排名聚合，如 ``workflows/cluster_208.json``。
    """
    sub = workflows_root / "workflows"
    if sub.is_dir():
        paths = sorted(p for p in sub.glob("*.json") if p.is_file())
        if paths:
            out: List[Tuple[str, Dict[str, Any]]] = []
            for p in paths:
                rel = f"workflows/{p.name}"
                with open(p, encoding="utf-8") as f:
                    out.append((rel, json.load(f)))
            return out
    merged = workflows_root / "workflows.json"
    if merged.is_file():
        with open(merged, encoding="utf-8") as f:
            arr = json.load(f)
        if isinstance(arr, list):
            return [(f"workflows.json#{i}", w) for i, w in enumerate(arr) if isinstance(w, dict)]
    return []


def _problem_blurb(wf: Dict[str, Any]) -> str:
    title = (wf.get("title") or "").strip()
    desc = (wf.get("description") or "").strip()
    parts = []
    if title:
        parts.append(f"标题: {title}")
    if desc:
        parts.append(f"描述: {desc}")
    prov = wf.get("provenance") or {}
    if isinstance(prov, dict):
        cid = prov.get("cluster_id")
        if cid is not None:
            parts.append(f"来源聚类簇: cluster_id={cid}")
        n = prov.get("n_chains")
        if n is not None:
            parts.append(f"簇内样本链数: {n}")
    return "\n".join(parts) if parts else "（未提供标题/描述）"


def _workflow_json_slice(wf: Dict[str, Any], max_chars: int) -> str:
    s = json.dumps(wf, ensure_ascii=False, indent=2)
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 20] + "\n…\n[truncated]"


def _all_pair_indices(n: int) -> List[Tuple[int, int]]:
    return [(i, j) for i in range(n) for j in range(i + 1, n)]


def _choose_pairs(
    n: int,
    mode: str,
    max_comparisons: int,
    seed: int,
) -> List[Tuple[int, int]]:
    if n < 2:
        return []
    all_pairs = _all_pair_indices(n)
    total = len(all_pairs)
    if mode == "exhaustive":
        if total > max_comparisons:
            print(
                f"[Step4] exhaustive 需要 {total} 对，超过 max_comparisons={max_comparisons}，"
                f"改为随机采样 {max_comparisons} 对",
                flush=True,
            )
            rng = random.Random(seed)
            return rng.sample(all_pairs, max_comparisons)
        return all_pairs
    rng = random.Random(seed)
    k = min(max_comparisons, total)
    return rng.sample(all_pairs, k)


def _build_compare_prompt(
    template: str,
    wf_a: Dict[str, Any],
    wf_b: Dict[str, Any],
    max_json_chars: int,
) -> str:
    return (
        template.replace("{{problem_a}}", _problem_blurb(wf_a))
        .replace("{{problem_b}}", _problem_blurb(wf_b))
        .replace("{{workflow_a_json}}", _workflow_json_slice(wf_a, max_json_chars))
        .replace("{{workflow_b_json}}", _workflow_json_slice(wf_b, max_json_chars))
    )


async def _compare_one(
    llm_fn,
    template: str,
    file_a: str,
    file_b: str,
    wf_a: Dict[str, Any],
    wf_b: Dict[str, Any],
    max_json_chars: int,
    semaphore: asyncio.Semaphore,
) -> Dict[str, Any]:
    prompt = _build_compare_prompt(template, wf_a, wf_b, max_json_chars)
    async with semaphore:
        t0 = time.perf_counter()
        raw = await llm_fn(prompt, temperature=0.1)
        dt = time.perf_counter() - t0
    parsed = _parse_compare_response(raw)
    better = str(parsed.get("better", "")).strip().upper()
    if better not in ("A", "B", "TIE"):
        better = "TIE"
    if better == "TIE":
        winner = None
    else:
        winner = file_a if better == "A" else file_b
    return {
        "file_a": file_a,
        "file_b": file_b,
        "workflow_id_a": wf_a.get("workflow_id"),
        "workflow_id_b": wf_b.get("workflow_id"),
        "better_raw": parsed.get("better"),
        "better": better if better != "TIE" else "tie",
        "winner_file": winner,
        "confidence": parsed.get("confidence"),
        "dimensions": parsed.get("dimensions"),
        "reason": parsed.get("reason"),
        "latency_sec": round(dt, 2),
        "raw_response_tail": raw[-800:] if len(raw) > 800 else raw,
    }


def _aggregate(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    W = defaultdict(lambda: {"wins": 0, "losses": 0, "ties": 0})
    for r in results:
        fa, fb = r["file_a"], r["file_b"]
        b = r.get("better", "tie")
        if b == "A":
            W[fa]["wins"] += 1
            W[fb]["losses"] += 1
        elif b == "B":
            W[fb]["wins"] += 1
            W[fa]["losses"] += 1
        else:
            W[fa]["ties"] += 1
            W[fb]["ties"] += 1
    rows = []
    for fid, c in W.items():
        score = c["wins"] - c["losses"]
        rows.append(
            {
                "file": fid,
                "wins": c["wins"],
                "losses": c["losses"],
                "ties": c["ties"],
                "score": score,
            }
        )
    rows.sort(key=lambda x: (-x["score"], -x["wins"], x["file"]))
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    return rows


async def run_step4_pipeline_async(config: Dict[str, Any]) -> Dict[str, Any]:
    print("\n" + "=" * 60, flush=True)
    print("Step4: Workflow 成对质量评估", flush=True)
    print("=" * 60, flush=True)

    data = config.get("data", {})
    llm_cfg = config.get("llm", {})
    runtime = config.get("runtime", {})
    prompt_path = config.get("prompt", {}).get("template_path", "prompts/step4_compare_workflows.md")

    workflows_root = Path(data.get("workflows_dir", "data/step3_output"))
    output_dir = Path(data.get("output_dir", "data/step4_output"))
    output_dir.mkdir(parents=True, exist_ok=True)
    verbose = bool(runtime.get("verbose", True))

    ret: Dict[str, Any] = {}
    try:
        entries = load_workflow_entries(workflows_root)
        n = len(entries)
        print(f"[Step4] 已加载 {n} 个 workflow（自 {workflows_root}）", flush=True)
        if n < 2:
            print("[Step4] 少于 2 个 workflow，跳过比较", flush=True)
            summary = {"n_workflows": n, "n_comparisons": 0, "skipped": True}
            with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            ret = summary
        else:
            mode = str(runtime.get("comparison_mode", "sampled")).lower()
            max_comp = int(runtime.get("max_comparisons", 400))
            seed = int(runtime.get("random_seed", 42))
            max_json_chars = int(runtime.get("max_json_chars_per_workflow", 24000))
            mw = max(1, int(runtime.get("max_workers", 10)))

            pairs = _choose_pairs(n, mode, max_comp, seed)
            print(
                f"[Step4] 比较模式={mode}，本轮对数={len(pairs)}，LLM 并发≤{mw}",
                flush=True,
            )

            template = _load_prompt_template(prompt_path)
            llm_fn = get_completion_fn(llm_cfg.get("provider", "gpt5_mini"))
            sem = asyncio.Semaphore(mw)

            tasks = [
                _compare_one(
                    llm_fn,
                    template,
                    entries[i][0],
                    entries[j][0],
                    entries[i][1],
                    entries[j][1],
                    max_json_chars,
                    sem,
                )
                for i, j in pairs
            ]

            results: List[Dict[str, Any]] = []
            done = 0
            step = max(1, len(tasks) // 20)
            for coro in asyncio.as_completed(tasks):
                try:
                    r = await coro
                except Exception as e:
                    r = {"error": repr(e)}
                results.append(r)
                done += 1
                if verbose and (done == 1 or done % step == 0 or done == len(tasks)):
                    print(f"  [Step4] 进度: {done}/{len(tasks)}", flush=True)

            ok = [r for r in results if "error" not in r]
            ranking = _aggregate(ok)

            results_path = output_dir / "comparisons.jsonl"
            with open(results_path, "w", encoding="utf-8") as f:
                for r in results:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")

            with open(output_dir / "ranking.json", "w", encoding="utf-8") as f:
                json.dump(ranking, f, ensure_ascii=False, indent=2)

            meta = {
                "workflows_root": str(workflows_root),
                "n_workflows": n,
                "n_pairs_requested": len(pairs),
                "n_comparisons_ok": len(ok),
                "n_comparisons_failed": len(results) - len(ok),
                "comparison_mode": mode,
                "max_comparisons": max_comp,
                "random_seed": seed,
            }
            with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            print(
                f"[Step4] 完成: 有效比较 {len(ok)}/{len(results)}，排名已写入 {output_dir / 'ranking.json'}",
                flush=True,
            )
            ret = {
                "meta": meta,
                "ranking": ranking[:5],
                "top_file": ranking[0]["file"] if ranking else None,
            }
    finally:
        from .chain_similarity import run_chain_similarity_eval_async

        await run_chain_similarity_eval_async(config, output_dir, verbose=verbose)

    return ret


_CLUSTER_JSON = re.compile(r"^cluster_(\d+)\.json$")


def _aligned_cluster_workflow_pairs(
    baseline_root: Path, variant_root: Path
) -> List[Tuple[str, Path, Path]]:
    """同名 cluster_*.json 在两侧均存在时返回 (cluster_id, baseline_path, variant_path)。"""
    b_sub = baseline_root / "workflows"
    v_sub = variant_root / "workflows"
    out: List[Tuple[str, Path, Path]] = []
    if not b_sub.is_dir() or not v_sub.is_dir():
        return out
    for bp in sorted(b_sub.glob("cluster_*.json")):
        m = _CLUSTER_JSON.match(bp.name)
        if not m:
            continue
        cid = m.group(1)
        vp = v_sub / bp.name
        if vp.is_file():
            out.append((cid, bp, vp))
    return out


def _cluster_ids_in_dir(workflows_root: Path) -> set[str]:
    sub = workflows_root / "workflows"
    if not sub.is_dir():
        return set()
    ids = set()
    for p in sub.glob("cluster_*.json"):
        m = _CLUSTER_JSON.match(p.name)
        if m:
            ids.add(m.group(1))
    return ids


async def compare_workflow_roots_aligned(
    baseline_root: Path,
    variant_root: Path,
    output_dir: Path,
    config: Dict[str, Any],
    *,
    baseline_tag: str = "baseline",
    variant_tag: str = "variant",
) -> Dict[str, Any]:
    """
    按簇 id 对齐：对每一对同名 ``workflows/cluster_<id>.json`` 调用 LLM，
    比较 **A=baseline** 与 **B=variant**（与 Step4 prompt 一致）。
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    llm_cfg = config.get("llm", {})
    runtime = config.get("runtime", {})
    prompt_path = config.get("prompt", {}).get(
        "template_path", "prompts/step4_compare_workflows.md"
    )
    max_json_chars = int(runtime.get("max_json_chars_per_workflow", 24000))
    verbose = bool(runtime.get("verbose", True))
    mw = max(1, int(runtime.get("max_workers", 20)))

    aligned = _aligned_cluster_workflow_pairs(baseline_root, variant_root)
    b_ids = _cluster_ids_in_dir(baseline_root)
    v_ids = _cluster_ids_in_dir(variant_root)
    only_b = sorted(b_ids - v_ids, key=int)
    only_v = sorted(v_ids - b_ids, key=int)

    print(
        f"[Ablation] 对齐簇数: {len(aligned)}；仅 baseline: {len(only_b)}；仅 variant: {len(only_v)}",
        flush=True,
    )
    if not aligned:
        summary = {
            "n_aligned": 0,
            "baseline_root": str(baseline_root),
            "variant_root": str(variant_root),
            "skipped": True,
            "only_baseline": only_b,
            "only_variant": only_v,
        }
        with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        return summary

    template = _load_prompt_template(prompt_path)
    llm_fn = get_completion_fn(llm_cfg.get("provider", "gpt5_mini"))
    sem = asyncio.Semaphore(mw)

    async def _one(cid: str, bp: Path, vp: Path) -> Dict[str, Any]:
        with open(bp, encoding="utf-8") as f:
            wf_a = json.load(f)
        with open(vp, encoding="utf-8") as f:
            wf_b = json.load(f)
        rel_a = f"{baseline_tag}/{bp.name}"
        rel_b = f"{variant_tag}/{vp.name}"
        r = await _compare_one(
            llm_fn,
            template,
            rel_a,
            rel_b,
            wf_a,
            wf_b,
            max_json_chars,
            sem,
        )
        r["cluster_id"] = int(cid)
        return r

    tasks = [asyncio.create_task(_one(cid, bp, vp)) for cid, bp, vp in aligned]
    results: List[Dict[str, Any]] = []
    done = 0
    step = max(1, len(tasks) // 20)
    for coro in asyncio.as_completed(tasks):
        try:
            r = await coro
        except Exception as e:
            r = {"error": repr(e)}
        results.append(r)
        done += 1
        if verbose and (done == 1 or done % step == 0 or done == len(tasks)):
            print(f"  [Ablation] 进度: {done}/{len(tasks)}", flush=True)

    ok = [r for r in results if "error" not in r]
    baseline_wins = sum(1 for r in ok if r.get("better") == "A")
    variant_wins = sum(1 for r in ok if r.get("better") == "B")
    ties = sum(1 for r in ok if r.get("better") == "tie")

    with open(output_dir / "comparisons.jsonl", "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    summary = {
        "kind": "ablation_aligned",
        "baseline_root": str(baseline_root),
        "variant_root": str(variant_root),
        "baseline_tag": baseline_tag,
        "variant_tag": variant_tag,
        "n_aligned": len(aligned),
        "n_comparisons_ok": len(ok),
        "n_comparisons_failed": len(results) - len(ok),
        "baseline_wins": baseline_wins,
        "variant_wins": variant_wins,
        "ties": ties,
        "note": "better=A 表示 baseline 更好，better=B 表示 variant 更好",
        "only_baseline_cluster_ids": only_b,
        "only_variant_cluster_ids": only_v,
    }
    with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(
        f"[Ablation] 完成: baseline 胜 {baseline_wins}, variant 胜 {variant_wins}, 平 {ties} "
        f"（有效 {len(ok)}/{len(results)}）→ {output_dir / 'summary.json'}",
        flush=True,
    )
    return summary


def run_step4_pipeline(config_path: str) -> Dict[str, Any]:
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return asyncio.run(run_step4_pipeline_async(config))


def load_config(config_path: str) -> Dict[str, Any]:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)
