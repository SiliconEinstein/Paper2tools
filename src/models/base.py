"""LLM provider base classes."""

from typing import Dict, Any


class LLMConfig:
    """YAML 配置的轻量包装，提供 provider 查找"""

    def __init__(self, config_data: Dict[str, Any]):
        self.providers = config_data.get('providers', {})

    def get_provider_config(self, name: str) -> Dict[str, Any]:
        return self.providers.get(name, {})
