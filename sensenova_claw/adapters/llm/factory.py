from __future__ import annotations

import logging
from typing import Callable

from sensenova_claw.platform.config.config import config
from sensenova_claw.adapters.llm.base import LLMProvider
from sensenova_claw.adapters.llm.providers.mock_provider import MockProvider

logger = logging.getLogger(__name__)


def _provider_config(provider_id: str) -> dict:
    cfg = config.get(f"llm.providers.{provider_id}", {})
    return cfg if isinstance(cfg, dict) else {}


def _has_api_key(provider_id: str) -> bool:
    """检查 provider_id 是否配置了有效的 api_key"""
    cfg = _provider_config(provider_id)
    key = str(cfg.get("api_key", ""))
    return bool(key) and not key.startswith("${")


class LLMFactory:
    # 所有已知 source_type 的工厂函数（供启动注册和动态注册共用）
    _PROVIDER_FACTORIES: dict[str, Callable[[str], LLMProvider]] = {}

    def __init__(self):
        # 立即实例化 mock（始终可用）
        self._providers: dict[str, LLMProvider] = {
            "mock": MockProvider(),
        }
        # 懒加载注册表：provider_id -> 工厂函数
        self._lazy: dict[str, Callable[[], LLMProvider]] = {}
        self._register_providers()

    def _register_providers(self) -> None:
        """注册所有 source_type，并为已配置 provider_id 建立懒加载表"""
        from sensenova_claw.adapters.llm.providers.anthropic_provider import AnthropicProvider
        from sensenova_claw.adapters.llm.providers.gemini_provider import GeminiProvider
        from sensenova_claw.adapters.llm.providers.openai_provider import OpenAIProvider

        self._PROVIDER_FACTORIES = {
            "openai": lambda provider_id: OpenAIProvider(provider_id, "openai"),
            "qwen": lambda provider_id: OpenAIProvider(provider_id, "qwen"),
            "deepseek": lambda provider_id: OpenAIProvider(provider_id, "deepseek"),
            "minimax": lambda provider_id: OpenAIProvider(provider_id, "minimax"),
            "glm": lambda provider_id: OpenAIProvider(provider_id, "glm"),
            "kimi": lambda provider_id: OpenAIProvider(provider_id, "kimi"),
            "step": lambda provider_id: OpenAIProvider(provider_id, "step"),
            "openai-compatible": lambda provider_id: OpenAIProvider(provider_id, "openai-compatible"),
            "anthropic": lambda provider_id: AnthropicProvider(provider_id, "anthropic"),
            "anthropic-compatible": lambda provider_id: AnthropicProvider(provider_id, "anthropic-compatible"),
            "gemini": lambda provider_id: GeminiProvider(provider_id, "gemini"),
            "gemini-compatible": lambda provider_id: GeminiProvider(provider_id, "gemini-compatible"),
        }

        for provider_id, provider_cfg in (config.get("llm.providers", {}) or {}).items():
            if provider_id == "mock" or not isinstance(provider_cfg, dict):
                continue
            source_type = str(provider_cfg.get("source_type", "") or "").strip()
            if source_type in self._PROVIDER_FACTORIES and _has_api_key(provider_id):
                self._lazy[provider_id] = lambda pid=provider_id, st=source_type: self._PROVIDER_FACTORIES[st](pid)

    def _build_provider(self, provider_id: str) -> LLMProvider:
        provider_cfg = _provider_config(provider_id)
        source_type = str(provider_cfg.get("source_type", "") or "").strip()
        if source_type not in self._PROVIDER_FACTORIES:
            raise RuntimeError(f"LLM provider '{provider_id}' 的 source_type 未配置或当前不可用")
        return self._PROVIDER_FACTORIES[source_type](provider_id)

    def get_provider(self, provider_name: str | None = None) -> LLMProvider:
        requested_provider = provider_name
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

        # 动态检测：config 热更新后可能新增了 provider_id
        provider_cfg = _provider_config(provider_name)
        source_type = str(provider_cfg.get("source_type", "") or "").strip()
        if _has_api_key(provider_name) and source_type in self._PROVIDER_FACTORIES:
            provider = self._build_provider(provider_name)
            self._providers[provider_name] = provider
            return provider

        if requested_provider:
            raise RuntimeError(f"LLM provider '{provider_name}' 未配置或当前不可用")

        return self._providers["mock"]

    async def start_config_listener(self, bus) -> None:
        """订阅 config.updated 事件，llm section 变更时重建 provider 表"""
        from sensenova_claw.kernel.events.bus import PublicEventBus  # noqa: F401
        from sensenova_claw.kernel.events.types import CONFIG_UPDATED
        async for event in bus.subscribe():
            if event.type == CONFIG_UPDATED and event.payload.get("section") == "llm":
                self._providers = {"mock": MockProvider()}
                self._lazy.clear()
                self._register_providers()
                logger.info("LLMFactory: providers reloaded due to config change")
