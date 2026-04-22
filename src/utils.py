"""Project utilities for config loading."""

from pathlib import Path
from typing import Optional
import yaml

from .models.base import LLMConfig

_CONFIG_CACHE: Optional[LLMConfig] = None


def get_config() -> LLMConfig:
    """Load and cache YAML config as LLMConfig."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    project_root = Path(__file__).resolve().parent.parent
    config_path = project_root / "configs" / "config.yaml"

    if not config_path.exists():
        _CONFIG_CACHE = LLMConfig({})
        return _CONFIG_CACHE

    with config_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    _CONFIG_CACHE = LLMConfig(data)
    return _CONFIG_CACHE
