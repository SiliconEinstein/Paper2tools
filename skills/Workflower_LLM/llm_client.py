"""LLM client for Workflower_LLM - self-contained, reads API key from .env"""

import asyncio
import os
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from openai import AsyncOpenAI
    import httpx
except ImportError:
    raise RuntimeError("pip install openai httpx")

try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
    from openai import APITimeoutError, APIConnectionError, InternalServerError, RateLimitError
    _llm_retry = retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type((
            APITimeoutError, APIConnectionError, InternalServerError, RateLimitError,
            httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError,
        )),
        reraise=True,
    )
except ImportError:
    def _llm_retry(fn): return fn


def _make_client() -> Optional[AsyncOpenAI]:
    api_key = os.environ.get("GPUGEEK_API_KEY", "").strip()
    base_url = os.environ.get("GPUGEEK_API_BASE", "").strip()
    if not api_key or not base_url:
        return None
    return AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        http_client=httpx.AsyncClient(
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            timeout=httpx.Timeout(360.0, connect=30.0),
        ),
    )


_client: Optional[AsyncOpenAI] = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = _make_client()
    if _client is None:
        raise RuntimeError("Set GPUGEEK_API_KEY and GPUGEEK_API_BASE in .env")
    return _client


@_llm_retry
async def llm(prompt: str, temperature: float = 0.3, max_tokens: int = 65535) -> str:
    """Single LLM call using GPT-5.2."""
    response = await get_client().chat.completions.create(
        model="Vendor2/GPT-5.2",
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_completion_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""


async def llm_parallel(prompts: list[str], temperature: float = 0.3) -> list[str]:
    """Run multiple LLM calls in parallel."""
    return await asyncio.gather(*[llm(p, temperature) for p in prompts])
