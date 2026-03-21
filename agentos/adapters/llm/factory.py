from __future__ import annotations

import logging
from typing import Callable

from agentos.platform.config.config import config
from agentos.adapters.llm.base import LLMProvider
from agentos.adapters.llm.providers.mock_provider import MockProvider

logger = logging.getLogger(__name__)


def _has_api_key(provider_key: str) -> bool:
    """检查 provider 是否配置了有效的 api_key"""
    cfg = config.get(f"llm.providers.{provider_key}", {})
    key = str(cfg.get("api_key", ""))
    return bool(key) and not key.startswith("${")


class LLMFactory:
    # 所有已知 provider 的工厂函数（供启动注册和动态注册共用）
    _PROVIDER_FACTORIES: dict[str, Callable[[], LLMProvider]] = {}

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

        self._PROVIDER_FACTORIES = {
            "openai":    lambda: OpenAIProvider("openai"),
            "anthropic": lambda: AnthropicProvider(),
            "gemini":    lambda: GeminiProvider(),
            "kimi":      lambda: OpenAIProvider("kimi"),
            "glm":       lambda: OpenAIProvider("glm"),
            "minimax":   lambda: OpenAIProvider("minimax"),
            "qwen":      lambda: OpenAIProvider("qwen"),
            "deepseek":  lambda: OpenAIProvider("deepseek"),
            "step":      lambda: OpenAIProvider("step"),
        }

        for name, factory in self._PROVIDER_FACTORIES.items():
            if _has_api_key(name):
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

        # 动态检测：config 热更新后可能新增了 provider（如 setup 配置）
        if _has_api_key(provider_name) and provider_name in self._PROVIDER_FACTORIES:
            provider = self._PROVIDER_FACTORIES[provider_name]()
            self._providers[provider_name] = provider
            return provider

        return self._providers["mock"]

    async def start_config_listener(self, bus) -> None:
        """订阅 config.updated 事件，llm section 变更时重建 provider 表"""
        from agentos.kernel.events.bus import PublicEventBus  # noqa: F401
        from agentos.kernel.events.types import CONFIG_UPDATED
        async for event in bus.subscribe():
            if event.type == CONFIG_UPDATED and event.payload.get("section") == "llm":
                self._providers = {"mock": MockProvider()}
                self._lazy.clear()
                self._register_providers()
                logger.info("LLMFactory: providers reloaded due to config change")
