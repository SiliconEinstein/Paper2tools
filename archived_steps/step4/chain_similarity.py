"""
Step4 子任务：簇内选中思维链的相似度评估（与 workflow 成对比较完全独立）。

- 向量：对簇内各链 embedding 做两两余弦相似度，汇总 max/min/mean/median。
- LLM：单次调用判断研究问题一致性、推理链路相似性（结构化 JSON）。
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..db import LanceVectorStore
from .llm_fn import get_completion_fn


def _load_prompt_template(template_path: str) -> str:
    path = Path(template_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / template_path
    return path.read_text(encoding="utf-8")


def _parse_json_llm_response(text: str) -> Dict[str, Any]:
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


def group_chains_by_cluster(rows: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    """按 cluster_id 分组；cluster_id 缺失的归入 -1。"""
    g: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict):
            continue
        cid = row.get("cluster_id")
        try:
            k = int(cid) if cid is not None else -1
        except (TypeError, ValueError):
            k = -1
        g[k].append(row)
    for k in g:
        g[k].sort(key=lambda r: (r.get("distance") is None, r.get("distance", 0.0)))
    return dict(g)


def pairwise_cosine_upper_triangle(vectors: np.ndarray) -> np.ndarray:
    """行向量为一条链的 embedding；返回上三角（不含对角）的余弦相似度一维数组。"""
    v = np.asarray(vectors, dtype=np.float64)
    if v.ndim != 2 or v.shape[0] < 2:
        return np.array([], dtype=np.float64)
    norms = np.linalg.norm(v, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    vn = v / norms
    sim = vn @ vn.T
    i, j = np.triu_indices(sim.shape[0], k=1)
    return sim[i, j]


def summarize_similarities(sims: np.ndarray) -> Dict[str, Any]:
    if sims.size == 0:
        return {
            "n_pairs": 0,
            "max": None,
            "min": None,
            "mean": None,
            "median": None,
        }
    return {
        "n_pairs": int(sims.size),
        "max": float(np.max(sims)),
        "min": float(np.min(sims)),
        "mean": float(np.mean(sims)),
        "median": float(np.median(sims)),
    }


def _build_numbered_chains_block(
    chains: List[Dict[str, Any]], max_chars_per_chain: int
) -> str:
    parts: List[str] = []
    for idx, ch in enumerate(chains, start=1):
        cid = ch.get("chain_id", "")
        pid = ch.get("paper_id", "")
        body = (ch.get("chain_text") or "").strip()
        if max_chars_per_chain > 0 and len(body) > max_chars_per_chain:
            body = body[: max_chars_per_chain - 20] + "\n…[truncated]"
        parts.append(
            f"### 链 {idx}\n"
            f"- chain_id: {cid}\n"
            f"- paper_id: {pid}\n\n"
            f"{body if body else '（无正文）'}\n"
        )
    return "\n".join(parts)


def _resolve_chain_similarity_config(config: Dict[str, Any]) -> Dict[str, Any]:
    root = config.get("chain_similarity") or {}
    data = config.get("data") or {}
    llm_root = config.get("llm") or {}
    out: Dict[str, Any] = {
        "enabled": bool(root.get("enabled", True)),
        "selected_chains_path": str(
            root.get("selected_chains_path")
            or data.get("selected_chains_path")
            or "data/step1_output/selected_chains.json"
        ),
        "lancedb_path": str(root.get("lancedb_path") or "data/lance_db"),
        "table_name": str(root.get("table_name") or "chain_embeddings"),
        "max_workers": max(1, int(root.get("max_workers", 8))),
        "max_chars_per_chain": int(root.get("max_chars_per_chain", 8000)),
        "prompt_path": str(
            (root.get("prompt") or {}).get("template_path")
            or "prompts/step4_evaluate_chain_similarity.md"
        ),
        "llm_provider": str((root.get("llm") or {}).get("provider") or llm_root.get("provider", "gpt5_mini")),
        "llm_temperature": float(
            (root.get("llm") or {}).get("temperature", llm_root.get("temperature", 0.1))
        ),
    }
    return out


async def _llm_one_cluster(
    llm_fn,
    template: str,
    cluster_id: int,
    chains: List[Dict[str, Any]],
    max_chars_per_chain: int,
    temperature: float,
    semaphore: asyncio.Semaphore,
) -> Dict[str, Any]:
    block = _build_numbered_chains_block(chains, max_chars_per_chain)
    prompt = (
        template.replace("{{cluster_id}}", str(cluster_id))
        .replace("{{n_chains}}", str(len(chains)))
        .replace("{{numbered_chains}}", block)
    )
    async with semaphore:
        t0 = time.perf_counter()
        raw = await llm_fn(prompt, temperature=temperature)
        dt = time.perf_counter() - t0
    try:
        parsed = _parse_json_llm_response(raw)
    except Exception as e:
        return {
            "cluster_id": cluster_id,
            "error": repr(e),
            "latency_sec": round(dt, 2),
            "raw_response_tail": raw[-1200:] if len(raw) > 1200 else raw,
        }
    out = {
        "cluster_id": cluster_id,
        "n_chains": len(chains),
        "latency_sec": round(dt, 2),
        "research_question_alignment": parsed.get("research_question_alignment"),
        "reasoning_path_similarity": parsed.get("reasoning_path_similarity"),
        "overall_chain_similarity": parsed.get("overall_chain_similarity"),
        "confidence": parsed.get("confidence"),
        "rationale_zh": parsed.get("rationale_zh"),
    }
    return out


async def run_chain_similarity_eval_async(
    config: Dict[str, Any],
    output_dir: Path,
    *,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    读取 selected_chains.json，按簇拉取向量并写:
    - chain_similarity/vector_metrics.json
    - chain_similarity/llm_judgments.jsonl
    - chain_similarity/summary.json
    """
    cs = _resolve_chain_similarity_config(config)
    out_root = Path(output_dir) / "chain_similarity"
    out_root.mkdir(parents=True, exist_ok=True)

    try:
        return await _run_chain_similarity_eval_impl(output_dir, verbose=verbose, cs=cs)
    except Exception as e:
        err = {"kind": "chain_similarity", "enabled": cs["enabled"], "fatal_error": repr(e)}
        with open(out_root / "summary.json", "w", encoding="utf-8") as f:
            json.dump(err, f, ensure_ascii=False, indent=2)
        if verbose:
            print(f"[Step4·思维链相似度] 未完整执行: {e}", flush=True)
        return err


async def _run_chain_similarity_eval_impl(
    output_dir: Path,
    *,
    verbose: bool,
    cs: Dict[str, Any],
) -> Dict[str, Any]:
    out_root = Path(output_dir) / "chain_similarity"
    out_root.mkdir(parents=True, exist_ok=True)

    if not cs["enabled"]:
        summary = {"enabled": False, "skipped": True}
        with open(out_root / "summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        if verbose:
            print("[Step4·思维链相似度] 已在配置中关闭 (chain_similarity.enabled=false)", flush=True)
        return summary

    sc_path = Path(cs["selected_chains_path"])
    if not sc_path.is_file():
        summary = {
            "enabled": True,
            "skipped": True,
            "reason": f"selected_chains 不存在: {sc_path}",
        }
        with open(out_root / "summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        if verbose:
            print(f"[Step4·思维链相似度] 跳过: {summary['reason']}", flush=True)
        return summary

    with open(sc_path, encoding="utf-8") as f:
        rows = json.load(f)
    if not isinstance(rows, list):
        summary = {"enabled": True, "skipped": True, "reason": "selected_chains 顶层不是数组"}
        with open(out_root / "summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        return summary

    by_c = group_chains_by_cluster(rows)
    if verbose:
        print(
            f"[Step4·思维链相似度] 已读 {len(rows)} 条链，{len(by_c)} 个簇；"
            f"Lance={cs['lancedb_path']} / {cs['table_name']}",
            flush=True,
        )

    db_path = Path(cs["lancedb_path"])
    store = LanceVectorStore(db_path=db_path, table_name=cs["table_name"])

    vector_records: List[Dict[str, Any]] = []
    llm_tasks: List[Tuple[int, List[Dict[str, Any]]]] = []

    for cluster_id, chains in sorted(by_c.items(), key=lambda x: x[0]):
        ids = [str(c.get("chain_id", "")) for c in chains if c.get("chain_id")]
        ids = [i for i in ids if i]
        fetched = store.fetch_by_ids_batched(ids, columns=["vector"], batch_size=500, verbose=False)
        vecs_list: List[np.ndarray] = []
        missing: List[str] = []
        order_ids: List[str] = []
        for cid in ids:
            rec = fetched.get(cid)
            if not rec or rec.get("vector") is None:
                missing.append(cid)
                continue
            vecs_list.append(np.asarray(rec["vector"], dtype=np.float32).ravel())
            order_ids.append(cid)
        if vecs_list:
            mat = np.stack(vecs_list, axis=0)
            sims = pairwise_cosine_upper_triangle(mat)
            vstats = summarize_similarities(sims)
        else:
            mat = np.zeros((0, 0), dtype=np.float32)
            sims = np.array([], dtype=np.float64)
            vstats = summarize_similarities(sims)

        vector_records.append(
            {
                "cluster_id": cluster_id,
                "n_chains_in_selection": len(chains),
                "n_chains_with_vector": len(vecs_list),
                "chain_ids_ordered": order_ids,
                "missing_vector_chain_ids": missing,
                "embedding_metric": "cosine",
                "pairwise_cosine": vstats,
            }
        )
        if len(chains) >= 2:
            llm_tasks.append((cluster_id, chains))

    vec_path = out_root / "vector_metrics.json"
    with open(vec_path, "w", encoding="utf-8") as f:
        json.dump(vector_records, f, ensure_ascii=False, indent=2)

    template = _load_prompt_template(cs["prompt_path"])
    llm_fn = get_completion_fn(cs["llm_provider"])
    sem = asyncio.Semaphore(cs["max_workers"])
    tasks = [
        asyncio.create_task(
            _llm_one_cluster(
                llm_fn,
                template,
                cid,
                chs,
                cs["max_chars_per_chain"],
                cs["llm_temperature"],
                sem,
            )
        )
        for cid, chs in llm_tasks
    ]

    llm_path = out_root / "llm_judgments.jsonl"
    llm_results: List[Dict[str, Any]] = []
    if tasks:
        llm_path.write_text("", encoding="utf-8")
    elif llm_path.exists():
        llm_path.unlink()

    done = 0
    step = max(1, len(tasks) // 10) if tasks else 1
    for coro in asyncio.as_completed(tasks):
        try:
            r = await coro
        except Exception as e:
            r = {"error": repr(e)}
        llm_results.append(r)
        with open(llm_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        done += 1
        if verbose and tasks and (done == 1 or done % step == 0 or done == len(tasks)):
            print(f"  [Step4·思维链相似度·LLM] 进度: {done}/{len(tasks)}", flush=True)

    n_vec = len(vector_records)
    n_llm_ok = sum(1 for r in llm_results if "error" not in r)
    summary = {
        "kind": "chain_similarity",
        "enabled": True,
        "selected_chains_path": str(sc_path.resolve()),
        "lancedb_path": str(db_path.resolve()),
        "table_name": cs["table_name"],
        "n_clusters": n_vec,
        "n_llm_calls": len(tasks),
        "n_llm_ok": n_llm_ok,
        "n_llm_failed": len(llm_results) - n_llm_ok,
        "outputs": {
            "vector_metrics": str(vec_path.resolve()),
            "llm_judgments": str(llm_path.resolve()) if tasks and llm_path.is_file() else None,
        },
        "note": "与 workflow 成对比较 (ranking.json) 完全独立；按簇评估簇内选中链。",
    }
    with open(out_root / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    if verbose:
        print(
            f"[Step4·思维链相似度] 完成: 向量簇数={n_vec}，LLM 有效 {n_llm_ok}/{len(tasks)} → {out_root}",
            flush=True,
        )
    try:
        store.close()
    except Exception:
        pass
    return summary
