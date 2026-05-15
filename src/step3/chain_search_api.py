"""
对外接口：思维链向量库检索 API。

设计目标：
- 对外只暴露明确的输入/输出协议。
- 内部多路召回与重排细节完全封装。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
import asyncio
import os
from pathlib import Path

import httpx

from ._chain_multi_recall import run_multi_recall_chain_search

_DEFAULT_EMBED_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"


def _load_env_from_dotenv_if_needed() -> None:
    """
    保障 step3 在独立执行时也能读到项目根目录 .env。
    优先使用 python-dotenv；若依赖不存在则走轻量兜底解析。
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


_load_env_from_dotenv_if_needed()


@dataclass
class ChainSearchRequest:
    """
    对外输入协议。
    """

    query: str
    top_k: int = 100
    table: str = "lkm_reasoning_chain_embeddings_v2"
    domain: Optional[str] = None
    # 是否允许在部分路由失败时降级返回
    allow_degraded: bool = True


@dataclass
class ChainSearchItem:
    chain_id: str
    paper_id: str
    conclusion_id: str
    conclusion_title: str
    conclusion_text: str
    reasoning_text: str
    num_steps: int
    created_at: str
    final_score: float
    route_hits: List[str] = field(default_factory=list)


@dataclass
class ChainSearchResponse:
    """
    对外输出协议。
    """

    query: str
    total: int
    degraded: bool
    enabled_routes: List[str]
    failed_routes: List[str]
    candidates: List[ChainSearchItem]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ChainSearchAPI:
    """
    对外唯一入口。
    """

    def __init__(self, config: Dict[str, Any]):
        _load_env_from_dotenv_if_needed()
        self.config = config
        self.chain_cfg = config.get("chain_search", {})

    async def search(self, req: ChainSearchRequest) -> ChainSearchResponse:
        if not req.query or not req.query.strip():
            raise ValueError("query 不能为空")
        if req.top_k <= 0:
            raise ValueError("top_k 必须 > 0")

        query_vec = await self._embed_query(req.query)

        internal = await run_multi_recall_chain_search(
            query=req.query,
            query_embedding=query_vec,
            table=req.table,
            ann_top_k=int(self.chain_cfg.get("ann_top_k", 1000)),
            lexical_top_k=int(self.chain_cfg.get("lexical_top_k", 800)),
            rule_top_k=int(self.chain_cfg.get("rule_top_k", 200)),
            final_top_k=req.top_k,
            weights=self.chain_cfg.get("weights", {"vector": 0.65, "lexical": 0.25, "rule": 0.10}),
            bytehouse=self.chain_cfg.get("bytehouse", {}),
        )

        degraded = bool(internal.get("degraded", False))
        enabled_routes = list(internal.get("enabled_routes", []))
        failed_routes = list(internal.get("failed_routes", []))
        route_errors = dict(internal.get("route_errors", {}))

        if not enabled_routes:
            raise RuntimeError(
                "链库检索失败：所有路由均不可用。"
                f" failed_routes={failed_routes}; route_errors={route_errors}"
            )

        if degraded and not req.allow_degraded:
            raise RuntimeError(
                f"链库检索发生降级，失败路由: {failed_routes}; route_errors={route_errors}"
            )

        candidates = [
            ChainSearchItem(
                chain_id=r.get("chain_id", ""),
                paper_id=r.get("paper_id", ""),
                conclusion_id=r.get("conclusion_id", ""),
                conclusion_title=r.get("conclusion_title", ""),
                conclusion_text=r.get("conclusion_text", ""),
                reasoning_text=r.get("reasoning_text", ""),
                num_steps=int(r.get("num_steps", 0)),
                created_at=r.get("created_at", ""),
                final_score=float(r.get("final_score", 0.0)),
                route_hits=list(r.get("route_hits", [])),
            )
            for r in internal.get("candidates", [])
        ]

        return ChainSearchResponse(
            query=req.query,
            total=len(candidates),
            degraded=degraded,
            enabled_routes=enabled_routes,
            failed_routes=failed_routes,
            candidates=candidates,
        )

    async def _embed_query(self, text: str) -> List[float]:
        _load_env_from_dotenv_if_needed()
        embed_cfg = self.chain_cfg.get("embedder", {})
        api_url = (embed_cfg.get("api_url") or os.getenv("API_URL") or _DEFAULT_EMBED_API_URL).strip()
        api_key = (
            embed_cfg.get("access_key")
            or os.getenv("DASHSCOPE_API_KEY")
            or os.getenv("ACCESS_KEY")
            or ""
        )
        model = embed_cfg.get("model", "text-embedding-v4")
        dimension = int(embed_cfg.get("dimension", 1024))
        timeout = int(embed_cfg.get("http_timeout", 20))

        if not api_key:
            raise ValueError(
                "embedding API key 未配置（DASHSCOPE_API_KEY / ACCESS_KEY）。"
                "请在环境变量或 .env 中设置。"
            )

        payload = {
            "model": model,
            "input": [text],
            "dimensions": dimension,
            "encoding_format": "float",
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(api_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            vec = data["data"][0]["embedding"]
            return [float(x) for x in vec]


def search_reasoning_chains(config: Dict[str, Any], req: ChainSearchRequest) -> ChainSearchResponse:
    """
    同步便捷入口（给 pipeline / script / agent 统一调用）。
    """
    api = ChainSearchAPI(config)
    return asyncio.run(api.search(req))

