"""Step4 共用的 LLM 调用入口（workflow 对比与思维链相似度等）。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Awaitable


def get_completion_fn(provider: str) -> Callable[..., Awaitable[str]]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from src.models.llm_providers import (
        gpt5_mini_completion,
        gpt_completion,
        gemini_completion,
    )

    mapping = {
        "gpt5_mini": gpt5_mini_completion,
        "gpt5": gpt_completion,
        "gemini": gemini_completion,
    }
    fn = mapping.get(provider)
    if fn is None:
        raise ValueError(f"Unknown LLM provider: {provider}")
    return fn
