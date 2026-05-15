"""
内部实现：思维链多路召回（ANN + lexical + rule）与融合重排。

注意：
- 该模块为内部实现细节，不建议被外部 agent 直接调用。
- 对外统一走 chain_search_api.py。
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
import os
import json
import re
from pathlib import Path

import httpx


@dataclass
class InternalChainHit:
    chain_id: str
    paper_id: str
    conclusion_id: str
    conclusion_title: str
    conclusion_text: str
    reasoning_text: str
    num_steps: int
    created_at: str
    vector_score: float = 0.0
    lexical_score: float = 0.0
    rule_score: float = 0.0
    final_score: float = 0.0
    route_hits: List[str] | None = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["route_hits"] = self.route_hits or []
        return d


def _escape_sql_string(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "''")


def _norm_minmax(scores: Dict[str, float]) -> Dict[str, float]:
    if not scores:
        return {}
    vals = list(scores.values())
    lo, hi = min(vals), max(vals)
    if abs(hi - lo) < 1e-9:
        return {k: (1.0 if v > 0 else 0.0) for k, v in scores.items()}
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


def _format_exc(e: Exception) -> str:
    msg = str(e).strip()
    if msg:
        return f"{type(e).__name__}: {msg}"
    return f"{type(e).__name__}: {repr(e)}"


def _load_env_from_dotenv_if_needed() -> None:
    """
    保障 step3 独立执行时可读取项目 .env（无 python-dotenv 也可用）。
    """
    try:
        from dotenv import load_dotenv  # type: ignore

        root = Path(__file__).resolve().parents[2]
        env_path = root / ".env"
        load_dotenv(dotenv_path=env_path, override=False)
        return
    except Exception:
        pass

    root = Path(__file__).resolve().parents[2]
    env_path = root / ".env"
    if not env_path.exists():
        return

    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


class _ByteHouseHttpClient:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None):
        _load_env_from_dotenv_if_needed()
        c = cfg or {}
        self.raw_endpoint = c.get("endpoint") or os.getenv("LKM_BYTEHOUSE_ENDPOINT", "")
        self.host = c.get("host") or os.getenv("LKM_BYTEHOUSE_HOST", "")
        self.user = c.get("user") or os.getenv("LKM_BYTEHOUSE_USER", "")
        self.password = c.get("password") or os.getenv("LKM_BYTEHOUSE_PASSWORD", "")
        self.database = c.get("database") or os.getenv("LKM_BYTEHOUSE_DATABASE", "")
        if "https" in c:
            self.https = bool(c.get("https"))
        else:
            env_https = os.getenv("LKM_BYTEHOUSE_HTTPS", "").strip().lower()
            self.https = env_https not in {"0", "false", "no"}
        self.port = c.get("port") or os.getenv("LKM_BYTEHOUSE_PORT", "")
        self.timeout_sec = int(c.get("timeout_sec", 20))
        missing = []
        if not self.host and not self.raw_endpoint:
            missing.append("LKM_BYTEHOUSE_HOST")
        if not self.user:
            missing.append("LKM_BYTEHOUSE_USER")
        if not self.password:
            missing.append("LKM_BYTEHOUSE_PASSWORD")
        if not self.database:
            missing.append("LKM_BYTEHOUSE_DATABASE")
        if missing:
            raise ValueError(
                "ByteHouse connection is not fully configured. Missing: "
                + ", ".join(missing)
                + "（可在环境变量或 .env 中配置）"
            )

        self.endpoints = self._build_endpoints()
        self.endpoint = self.endpoints[0]
        self.client = httpx.AsyncClient(timeout=self.timeout_sec)

    def _build_endpoints(self) -> List[str]:
        if self.raw_endpoint:
            if "?" in self.raw_endpoint:
                return [self.raw_endpoint]
            return [f"{self.raw_endpoint}?database={self.database}"]

        if self.host.startswith("http://") or self.host.startswith("https://"):
            base = self.host
            if "?" in base:
                return [base]
            return [f"{base}/?database={self.database}"]

        endpoints: List[str] = []
        if self.port:
            scheme = "https" if self.https else "http"
            endpoints.append(f"{scheme}://{self.host}:{self.port}/?database={self.database}")
            return endpoints

        if self.https:
            endpoints.append(f"https://{self.host}/?database={self.database}")
            endpoints.append(f"http://{self.host}:8123/?database={self.database}")
            endpoints.append(f"http://{self.host}/?database={self.database}")
        else:
            endpoints.append(f"http://{self.host}/?database={self.database}")
            endpoints.append(f"http://{self.host}:8123/?database={self.database}")
            endpoints.append(f"https://{self.host}/?database={self.database}")
        return endpoints

    async def query_json_each_row(self, sql: str) -> List[Dict[str, Any]]:
        payload = f"{sql}\nFORMAT JSONEachRow"
        last_err = None
        resp = None
        errors: List[str] = []
        for ep in self.endpoints:
            try:
                resp = await self.client.post(
                    ep,
                    content=payload.encode("utf-8"),
                    auth=(self.user, self.password),
                    headers={"Content-Type": "text/plain; charset=utf-8"},
                )
                self.endpoint = ep
                break
            except (httpx.ConnectTimeout, httpx.ConnectError, httpx.ReadTimeout, httpx.NetworkError) as e:
                last_err = e
                errors.append(f"{ep} -> {type(e).__name__}")
                continue
        if resp is None:
            raise RuntimeError(
                "ByteHouse endpoint unreachable. Tried: "
                + "; ".join(errors)
                + f". Last error: {_format_exc(last_err or RuntimeError('unknown'))}"
            )
        if resp.status_code >= 400:
            text = resp.text[:500].replace("\n", " ")
            raise RuntimeError(f"ByteHouse HTTP {resp.status_code}: {text}")
        lines = [x for x in resp.text.splitlines() if x.strip()]
        try:
            return [json.loads(x) for x in lines]
        except json.JSONDecodeError as e:
            text = resp.text[:500].replace("\n", " ")
            raise RuntimeError(f"ByteHouse parse error: {e}. Raw: {text}") from e

    async def close(self):
        await self.client.aclose()


async def run_multi_recall_chain_search(
    *,
    query: str,
    query_embedding: List[float],
    table: str,
    ann_top_k: int = 1000,
    lexical_top_k: int = 800,
    rule_top_k: int = 200,
    final_top_k: int = 100,
    weights: Optional[Dict[str, float]] = None,
    bytehouse: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    内部多路召回主函数。
    """
    weights = weights or {"vector": 0.65, "lexical": 0.25, "rule": 0.10}
    wv = float(weights.get("vector", 0.65))
    wl = float(weights.get("lexical", 0.25))
    wr = float(weights.get("rule", 0.10))

    client = _ByteHouseHttpClient(bytehouse)
    try:
        failed_routes: List[str] = []
        route_errors: Dict[str, str] = {}
        ann_query_embedding = query_embedding
        try:
            table_dim = await _detect_embedding_dim(client, table)
            ann_query_embedding = _align_embedding_dim(query_embedding, table_dim)
        except Exception:
            # 维度探测失败时使用原始向量，交给 ANN 路由自身报错
            ann_query_embedding = query_embedding
        try:
            ann_hits = await _ann_recall(client, table, ann_query_embedding, ann_top_k)
        except Exception as e:
            ann_hits = {}
            failed_routes.append("ann")
            route_errors["ann"] = _format_exc(e)
        try:
            lexical_hits = await _lexical_recall(client, table, query, lexical_top_k)
        except Exception as e:
            lexical_hits = {}
            failed_routes.append("lexical")
            route_errors["lexical"] = _format_exc(e)
        try:
            rule_hits = await _rule_recall(client, table, query, rule_top_k)
        except Exception as e:
            rule_hits = {}
            failed_routes.append("rule")
            route_errors["rule"] = _format_exc(e)

        merged = _merge_hits(ann_hits, lexical_hits, rule_hits)
        if not merged:
            return {
                "candidates": [],
                "degraded": True,
                "failed_routes": failed_routes,
                "enabled_routes": [],
                "route_errors": route_errors,
            }

        vmap = _norm_minmax({k: v.vector_score for k, v in merged.items()})
        lmap = _norm_minmax({k: v.lexical_score for k, v in merged.items()})
        rmap = _norm_minmax({k: v.rule_score for k, v in merged.items()})

        ranked: List[InternalChainHit] = []
        for cid, h in merged.items():
            h.vector_score = vmap.get(cid, 0.0)
            h.lexical_score = lmap.get(cid, 0.0)
            h.rule_score = rmap.get(cid, 0.0)
            h.final_score = wv * h.vector_score + wl * h.lexical_score + wr * h.rule_score
            ranked.append(h)

        ranked.sort(key=lambda x: x.final_score, reverse=True)
        out = [x.to_dict() for x in ranked[:final_top_k]]
        enabled = [r for r in ["ann", "lexical", "rule"] if r not in failed_routes]
        return {
            "candidates": out,
            "degraded": len(failed_routes) > 0,
            "failed_routes": failed_routes,
            "enabled_routes": enabled,
            "route_errors": route_errors,
        }
    finally:
        await client.close()

async def _ann_recall(
    client: _ByteHouseHttpClient,
    table: str,
    query_embedding: List[float],
    top_k: int,
) -> Dict[str, InternalChainHit]:
    vec_literal = ",".join(f"{float(x):.8f}" for x in query_embedding)
    sql = f"""
SELECT
  chain_id, paper_id, conclusion_id, conclusion_title, conclusion_text,
  reasoning_text, num_steps, created_at,
  1.0 - dist AS vector_score
FROM
(
  SELECT
    chain_id, paper_id, conclusion_id, conclusion_title, conclusion_text,
    reasoning_text, num_steps, created_at,
    cosineDistance(embedding, [{vec_literal}]) AS dist
  FROM {table}
  ORDER BY dist ASC
  LIMIT {top_k}
)
"""
    rows = await client.query_json_each_row(sql)
    out: Dict[str, InternalChainHit] = {}
    for r in rows:
        cid = str(r.get("chain_id", ""))
        if not cid:
            continue
        out[cid] = InternalChainHit(
            chain_id=cid,
            paper_id=str(r.get("paper_id", "")),
            conclusion_id=str(r.get("conclusion_id", "")),
            conclusion_title=r.get("conclusion_title", ""),
            conclusion_text=r.get("conclusion_text", ""),
            reasoning_text=r.get("reasoning_text", ""),
            num_steps=int(r.get("num_steps", 0)),
            created_at=str(r.get("created_at", "")),
            vector_score=float(r.get("vector_score", 0.0)),
            route_hits=["ann"],
        )
    return out


async def _lexical_recall(
    client: _ByteHouseHttpClient,
    table: str,
    query: str,
    top_k: int,
) -> Dict[str, InternalChainHit]:
    kws = list(dict.fromkeys(re.findall(r"[\u4e00-\u9fffA-Za-z0-9\-\+]{2,}", query.lower())))[:8]
    if not kws:
        return {}
    conds = []
    for kw in kws:
        k = _escape_sql_string(kw)
        conds.append(
            f"(positionCaseInsensitiveUTF8(conclusion_title, '{k}') > 0)"
            f" + (positionCaseInsensitiveUTF8(conclusion_text, '{k}') > 0)"
            f" + (positionCaseInsensitiveUTF8(reasoning_text, '{k}') > 0)"
        )
    expr = " + ".join(conds)
    sql = f"""
SELECT
  chain_id, paper_id, conclusion_id, conclusion_title, conclusion_text,
  reasoning_text, num_steps, created_at,
  lexical_raw AS lexical_score
FROM
(
  SELECT
    chain_id, paper_id, conclusion_id, conclusion_title, conclusion_text,
    reasoning_text, num_steps, created_at,
    ({expr}) AS lexical_raw
  FROM {table}
)
WHERE lexical_raw > 0
ORDER BY lexical_raw DESC
LIMIT {top_k}
"""
    rows = await client.query_json_each_row(sql)
    out: Dict[str, InternalChainHit] = {}
    for r in rows:
        cid = str(r.get("chain_id", ""))
        if not cid:
            continue
        out[cid] = InternalChainHit(
            chain_id=cid,
            paper_id=str(r.get("paper_id", "")),
            conclusion_id=str(r.get("conclusion_id", "")),
            conclusion_title=r.get("conclusion_title", ""),
            conclusion_text=r.get("conclusion_text", ""),
            reasoning_text=r.get("reasoning_text", ""),
            num_steps=int(r.get("num_steps", 0)),
            created_at=str(r.get("created_at", "")),
            lexical_score=float(r.get("lexical_score", 0.0)),
            route_hits=["lexical"],
        )
    return out


async def _rule_recall(
    client: _ByteHouseHttpClient,
    table: str,
    query: str,
    top_k: int,
) -> Dict[str, InternalChainHit]:
    seeds = list(dict.fromkeys(re.findall(r"[\u4e00-\u9fffA-Za-z0-9\-\+]{2,}", query)))[:6]
    if not seeds:
        return {}
    conds = []
    for s in seeds:
        k = _escape_sql_string(s)
        conds.append(
            f"(positionCaseInsensitiveUTF8(conclusion_title, '{k}') > 0)"
            f" + (positionCaseInsensitiveUTF8(conclusion_text, '{k}') > 0)"
        )
    expr = " + ".join(conds)
    sql = f"""
SELECT
  chain_id, paper_id, conclusion_id, conclusion_title, conclusion_text,
  reasoning_text, num_steps, created_at,
  rule_raw AS rule_score
FROM
(
  SELECT
    chain_id, paper_id, conclusion_id, conclusion_title, conclusion_text,
    reasoning_text, num_steps, created_at,
    ({expr}) AS rule_raw
  FROM {table}
)
WHERE rule_raw > 0
ORDER BY rule_raw DESC
LIMIT {top_k}
"""
    rows = await client.query_json_each_row(sql)
    out: Dict[str, InternalChainHit] = {}
    for r in rows:
        cid = str(r.get("chain_id", ""))
        if not cid:
            continue
        out[cid] = InternalChainHit(
            chain_id=cid,
            paper_id=str(r.get("paper_id", "")),
            conclusion_id=str(r.get("conclusion_id", "")),
            conclusion_title=r.get("conclusion_title", ""),
            conclusion_text=r.get("conclusion_text", ""),
            reasoning_text=r.get("reasoning_text", ""),
            num_steps=int(r.get("num_steps", 0)),
            created_at=str(r.get("created_at", "")),
            rule_score=float(r.get("rule_score", 0.0)),
            route_hits=["rule"],
        )
    return out


def _merge_hits(
    ann_hits: Dict[str, InternalChainHit],
    lexical_hits: Dict[str, InternalChainHit],
    rule_hits: Dict[str, InternalChainHit],
) -> Dict[str, InternalChainHit]:
    out: Dict[str, InternalChainHit] = {}
    for source in (ann_hits, lexical_hits, rule_hits):
        for cid, h in source.items():
            if cid not in out:
                out[cid] = h
                continue
            c = out[cid]
            c.vector_score = max(c.vector_score, h.vector_score)
            c.lexical_score = max(c.lexical_score, h.lexical_score)
            c.rule_score = max(c.rule_score, h.rule_score)
            c.route_hits = sorted(set((c.route_hits or []) + (h.route_hits or [])))
    return out


async def _detect_embedding_dim(client: _ByteHouseHttpClient, table: str) -> int:
    sql = f"SELECT length(embedding) AS dim FROM {table} LIMIT 1"
    rows = await client.query_json_each_row(sql)
    if not rows:
        raise RuntimeError("cannot detect embedding dim: empty table")
    dim = int(rows[0].get("dim", 0))
    if dim <= 0:
        raise RuntimeError(f"invalid embedding dim: {dim}")
    return dim


def _align_embedding_dim(vec: List[float], target_dim: int) -> List[float]:
    if target_dim <= 0:
        return vec
    if len(vec) == target_dim:
        return vec
    if len(vec) > target_dim:
        return vec[:target_dim]
    # 长度不足则尾部补 0，避免因维度不一致导致 ANN 失败
    return vec + [0.0] * (target_dim - len(vec))

