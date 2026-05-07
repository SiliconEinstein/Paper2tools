"""LLM provider implementations - 精简版"""

import json
import os
from typing import Optional

try:
    from openai import AsyncOpenAI
    import httpx
except ImportError:
    raise RuntimeError("openai package required. Run: pip install openai httpx")

try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
except ImportError:
    retry = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from src.utils import get_config
except ImportError:
    from utils import get_config


# ============================================================================
# Configuration
# ============================================================================

def _get_env_or_config(provider: str, key: str, env_var: str) -> str:
    """从环境变量或配置文件获取值，环境变量优先"""
    env_val = os.environ.get(env_var, "").strip()
    if env_val:
        return env_val

    try:
        config = get_config()
        provider_cfg = config.get_provider_config(provider)
        return provider_cfg.get(key, "").strip()
    except Exception:
        return ""


# GPUGeek API 配置（用于 GPT-5 系列）
_GPUGEEK_API_KEY = _get_env_or_config("gpt5", "api_key", "GPUGEEK_API_KEY")
_GPUGEEK_BASE_URL = _get_env_or_config("gpt5", "base_url", "GPUGEEK_API_BASE")

# 创建 OpenAI 客户端
_async_client = AsyncOpenAI(
    api_key=_GPUGEEK_API_KEY,
    base_url=_GPUGEEK_BASE_URL,
    http_client=httpx.AsyncClient(
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        timeout=httpx.Timeout(360.0, connect=30.0),
    ),
) if _GPUGEEK_API_KEY and _GPUGEEK_BASE_URL else None


# ============================================================================
# Retry Logic
# ============================================================================

try:
    from openai import (
        APITimeoutError,
        APIConnectionError,
        InternalServerError,
        RateLimitError,
    )
    _RETRIABLE = (
        APITimeoutError,
        APIConnectionError,
        InternalServerError,
        RateLimitError,
        httpx.ReadTimeout,
        httpx.ConnectTimeout,
        httpx.ConnectError,
        TimeoutError,
        ConnectionError,
    )
except ImportError:
    _RETRIABLE = (
        httpx.ReadTimeout,
        httpx.ConnectTimeout,
        httpx.ConnectError,
        TimeoutError,
        ConnectionError,
    )

if retry is not None:
    _llm_retry = retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type(_RETRIABLE),
        reraise=True,
    )
else:
    def _llm_retry(fn):
        return fn


# ============================================================================
# LLM Functions
# ============================================================================

@_llm_retry
async def gpt5_mini_completion(
    prompt: str,
    temperature: float = 0.7,
    **kwargs
) -> str:
    """
    GPT-5-mini completion

    Args:
        prompt: 输入 prompt
        temperature: 温度参数 (0-1)
        **kwargs: 其他参数传递给 OpenAI API

    Returns:
        LLM 响应文本
    """
    if _async_client is None:
        raise RuntimeError(
            "GPUGeek API not configured. Set GPUGEEK_API_KEY and GPUGEEK_API_BASE "
            "in environment or configs/config.yaml"
        )

    messages = [{"role": "user", "content": prompt}]
    response = await _async_client.chat.completions.create(
        model="Vendor2/GPT-5-mini",
        messages=messages,
        temperature=temperature,
        max_completion_tokens=kwargs.pop("max_tokens", 65535),
        **kwargs
    )
    content = response.choices[0].message.content
    return content or ""


@_llm_retry
async def gpt_completion(
    prompt: str,
    temperature: float = 0.7,
    **kwargs
) -> str:
    """
    GPT-5.2 completion

    Args:
        prompt: 输入 prompt
        temperature: 温度参数 (0-1)
        **kwargs: 其他参数传递给 OpenAI API

    Returns:
        LLM 响应文本
    """
    if _async_client is None:
        raise RuntimeError(
            "GPUGeek API not configured. Set GPUGEEK_API_KEY and GPUGEEK_API_BASE "
            "in environment or configs/config.yaml"
        )

    messages = [{"role": "user", "content": prompt}]
    response = await _async_client.chat.completions.create(
        model="Vendor2/GPT-5.2",
        messages=messages,
        temperature=temperature,
        max_completion_tokens=kwargs.pop("max_tokens", 65535),
        **kwargs
    )
    content = response.choices[0].message.content
    return content or ""


# ============================================================================
# Gemini (通过 LiteLLM)
# ============================================================================

try:
    import litellm
    litellm.suppress_debug_info = True
    _HAS_LITELLM = True
except ImportError:
    _HAS_LITELLM = False


@_llm_retry
async def gemini_completion(prompt: str, **kwargs) -> str:
    """
    Gemini completion via LiteLLM proxy

    需要配置 LITELLM_PROXY_API_BASE 和 LITELLM_PROXY_API_KEY
    """
    if not _HAS_LITELLM:
        raise RuntimeError("litellm not installed. Run: pip install litellm")

    # 从环境变量或配置读取
    api_base = _get_env_or_config("gemini", "base_url", "LITELLM_PROXY_API_BASE")
    api_key = _get_env_or_config("gemini", "api_key", "LITELLM_PROXY_API_KEY")

    if not api_key:
        raise RuntimeError(
            "LiteLLM not configured. Set LITELLM_PROXY_API_KEY and "
            "LITELLM_PROXY_API_BASE in environment or configs/config.yaml"
        )

    # 设置环境变量供 litellm 使用
    if api_base:
        os.environ["LITELLM_PROXY_API_BASE"] = api_base
    os.environ["LITELLM_PROXY_API_KEY"] = api_key

    messages = [{"role": "user", "content": prompt}]
    response = await litellm.acompletion(
        model="litellm_proxy/gemini-3-flash-preview",
        messages=messages,
        **kwargs
    )
    msg = response["choices"][0]["message"]
    content = msg.get("content") if isinstance(msg, dict) else None
    return content or ""
