from __future__ import annotations

from typing import Callable

from agentos.platform.config.config import config
from agentos.adapters.llm.base import LLMProvider
from agentos.adapters.llm.providers.mock_provider import MockProvider


def _has_api_key(provider_key: str) -> bool:
    """检查 provider 是否配置了有效的 api_key"""
    cfg = config.get(f"llm.providers.{provider_key}", {})
    key = cfg.get("api_key", "")
    return bool(key) and not key.startswith("${")


class LLMFactory:
    def __init__(self):
        # 立即实例化 mock（始终可用）
        self._providers: dict[str, LLMProvider] = {
            "mock": MockProvider(),
        }
        # 懒加载注册表：provider_name -> 工厂函数
        self._lazy: dict[str, Callable[[], LLMProvider]] = {}
        self._register_providers()

    def _register_providers(self) -> None:
        """注册所有 provider，仅配置了 api_key 的才加入懒加载表"""
        from agentos.adapters.llm.providers.anthropic_provider import AnthropicProvider
        from agentos.adapters.llm.providers.gemini_provider import GeminiProvider
        from agentos.adapters.llm.providers.openai_provider import OpenAIProvider

        # (provider_name, 工厂函数, config 中的 provider key)
        registry: list[tuple[str, Callable[[], LLMProvider], str]] = [
            ("openai",    lambda: OpenAIProvider("openai"),    "openai"),
            ("anthropic", lambda: AnthropicProvider(),         "anthropic"),
            ("gemini",    lambda: GeminiProvider(),            "gemini"),
            ("kimi",      lambda: OpenAIProvider("kimi"),      "kimi"),
            ("glm",       lambda: OpenAIProvider("glm"),       "glm"),
            ("minimax",   lambda: OpenAIProvider("minimax"),   "minimax"),
            ("qwen",      lambda: OpenAIProvider("qwen"),      "qwen"),
            ("deepseek",  lambda: OpenAIProvider("deepseek"),  "deepseek"),
            ("step",      lambda: OpenAIProvider("step"),      "step"),
        ]

        for name, factory, cfg_key in registry:
            if _has_api_key(cfg_key):
                self._lazy[name] = factory

    def get_provider(self, provider_name: str | None = None) -> LLMProvider:
        if not provider_name:
            provider_name, _ = config.resolve_model()

        # 已实例化的直接返回
        if provider_name in self._providers:
            return self._providers[provider_name]

        # 懒加载：首次使用时实例化
        if provider_name in self._lazy:
            provider = self._lazy[provider_name]()
            self._providers[provider_name] = provider
            del self._lazy[provider_name]
            return provider

        return self._providers["mock"]
