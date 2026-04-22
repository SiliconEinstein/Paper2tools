"""
向量化模块 - 适配 DashScope Embedding API
借鉴 gaia-lkm 的 worker pool + jitter backoff 设计
"""

import asyncio
import logging
import os
import random
import time
from typing import List, Dict
import numpy as np
import httpx

from .data_loader import ReasoningChain
from ..db import LanceVectorStore

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

_DEFAULT_EMBED_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"


class DashScopeEmbedder:
    """DashScope Embedding API 客户端，worker pool 限速 + jitter backoff"""

    def __init__(self, config: Dict):
        self.api_url = (
            (config.get("api_url") or os.environ.get("API_URL") or _DEFAULT_EMBED_API_URL).strip()
        )
        self.api_key = (
            config.get("access_key")
            or os.environ.get("DASHSCOPE_API_KEY")
            or os.environ.get("ACCESS_KEY")
            or ""
        )
        self.model = config.get("model", "text-embedding-v4")
        self.dimension = config.get("dimension", 1024)
        self.n_workers = config.get("concurrency", 50)
        self.max_retries = config.get("max_retries", 5)
        self.timeout = config.get("http_timeout", 30)
        self.max_text_length = config.get("max_text_length", 8000)  # 字符数限制

        if not self.api_key:
            raise ValueError("DashScope API key not configured")

        self._client = httpx.AsyncClient(timeout=self.timeout)
        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def _truncate_text(self, text: str) -> str:
        """截断超长文本"""
        if len(text) > self.max_text_length:
            return text[:self.max_text_length]
        return text

    async def _call_api(self, text: str) -> List[float]:
        """单次 API 调用，带 jitter backoff 重试"""
        text = self._truncate_text(text)
        last_exc = None

        for attempt in range(self.max_retries):
            try:
                resp = await self._client.post(
                    self.api_url,
                    json={
                        "model": self.model,
                        "input": [text],
                        "dimensions": self.dimension,
                        "encoding_format": "float"
                    },
                    headers=self._headers
                )
                resp.raise_for_status()
                data = resp.json()
                if "data" not in data:
                    raise ValueError(f"API returned no 'data' field: {data}")
                return data["data"][0]["embedding"]

            except (httpx.HTTPError, KeyError, ValueError) as exc:
                last_exc = exc
                if attempt < self.max_retries - 1:
                    # Jitter backoff: 0.5s, 1.5s, 3.5s, 7.5s...
                    delay = (0.5 * (2 ** attempt)) + random.uniform(0, 0.5)
                    await asyncio.sleep(delay)

        raise last_exc

    async def embed_batch(
        self,
        items: List[tuple],  # (chain_id, chain_text, metadata)
        on_result,
        on_error
    ):
        """Worker pool 并发处理，限速"""
        queue = asyncio.Queue()
        for item in items:
            queue.put_nowait(item)
        for _ in range(self.n_workers):
            queue.put_nowait(None)  # Sentinel

        async def worker():
            while True:
                item = await queue.get()
                if item is None:
                    return
                chain_id, chain_text, metadata = item
                try:
                    vector = await self._call_api(chain_text)
                    await on_result(chain_id, vector, metadata)
                except Exception as exc:
                    await on_error(chain_id, exc)

        await asyncio.gather(*[worker() for _ in range(self.n_workers)])

    async def close(self):
        await self._client.aclose()


def create_embedder(config: Dict) -> DashScopeEmbedder:
    return DashScopeEmbedder(config)


async def vectorize_reasoning_chains(
    chains: List[ReasoningChain],
    embedder: DashScopeEmbedder,
    vector_store: LanceVectorStore,
    batch_size: int = 5000,
    verbose: bool = True
) -> int:
    """以思维链为单位向量化"""

    # 1. 构建待向量化列表
    all_chains = {}
    for chain in chains:
        chain_id = f"{chain.paper_id}_{chain.conclusion_id}"
        step_texts = [f"Step {step.step_id}: {step.text}" for step in chain.steps]
        chain_text = "\n".join(step_texts)

        all_chains[chain_id] = (
            chain_text,
            {
                "paper_id": chain.paper_id,
                "journal": chain.journal,
                "conclusion_id": chain.conclusion_id,
                "conclusion_title": chain.conclusion_title,
                "chain_text": chain_text[:2000],
                "cluster_id": -1,
                "num_steps": len(chain.steps),
                "has_citations": any(s.has_citations for s in chain.steps),
                "has_figures": any(s.has_figures for s in chain.steps),
            }
        )

    if verbose:
        print(f"\nTotal chains: {len(all_chains)}")

    # 2. 过滤已存在的
    try:
        arrow_table = vector_store.table.to_arrow()
        existing_ids = set(arrow_table.column("chain_id").to_pylist())
    except Exception:
        existing_ids = set()

    new_ids = [cid for cid in all_chains if cid not in existing_ids]

    if verbose:
        print(f"  Existing in LanceDB: {len(all_chains) - len(new_ids)}")
        print(f"  New chains to embed: {len(new_ids)}")

    if not new_ids:
        print("All chains already vectorized. Skipping.")
        return 0

    # 3. 分 chunk 处理
    n_chunks = (len(new_ids) + batch_size - 1) // batch_size
    total_success = 0
    total_failed = 0
    pipeline_start = time.monotonic()
    chunk_times = []

    for chunk_idx in range(n_chunks):
        chunk_start = time.monotonic()
        start = chunk_idx * batch_size
        end = min(start + batch_size, len(new_ids))
        chunk_ids = new_ids[start:end]

        items = [(cid, *all_chains[cid]) for cid in chunk_ids]

        results = {}
        failed_ids = []

        async def on_result(chain_id, vector, metadata):
            results[chain_id] = (vector, metadata)

        async def on_error(chain_id, exc):
            failed_ids.append(chain_id)
            logger.warning(f"Embedding failed for {chain_id}: {exc}")

        await embedder.embed_batch(items, on_result, on_error)

        # 写入 LanceDB
        for cid, (vector, meta) in results.items():
            vector_store.add_vectors(
                [cid],
                np.array([vector], dtype=np.float32),
                [meta]
            )
        vector_store.flush()

        chunk_success = len(results)
        chunk_failed = len(failed_ids)
        total_success += chunk_success
        total_failed += chunk_failed

        # 进度 & ETA
        chunk_elapsed = time.monotonic() - chunk_start
        chunk_times.append(chunk_elapsed)
        avg_chunk_time = sum(chunk_times) / len(chunk_times)
        remaining = n_chunks - chunk_idx - 1
        eta_min = (avg_chunk_time * remaining) / 60
        rps = chunk_success / chunk_elapsed if chunk_elapsed > 0 else 0

        if verbose:
            print(
                f"  Chunk {chunk_idx+1}/{n_chunks}: "
                f"{chunk_success} ok, {chunk_failed} fail | "
                f"{chunk_elapsed:.0f}s ({rps:.0f} RPS) | "
                f"cumulative {total_success}/{len(new_ids)} | "
                f"ETA {eta_min:.0f}min"
            )

    total_elapsed = time.monotonic() - pipeline_start
    if verbose:
        print(f"\nVectorization complete in {total_elapsed:.0f}s:")
        print(f"  Success: {total_success}")
        print(f"  Failed: {total_failed}")
        avg_rps = total_success / total_elapsed if total_elapsed > 0 else 0
        print(f"  Avg RPS: {avg_rps:.1f}")

    return total_success
