from __future__ import annotations

from agentos.platform.config.config import config
from agentos.adapters.llm.base import LLMProvider
from agentos.adapters.llm.providers.anthropic_provider import AnthropicProvider
from agentos.adapters.llm.providers.gemini_provider import GeminiProvider
from agentos.adapters.llm.providers.mock_provider import MockProvider
from agentos.adapters.llm.providers.openai_provider import OpenAIProvider


class LLMFactory:
    def __init__(self):
        self._providers: dict[str, LLMProvider] = {
            "mock": MockProvider(),
            "openai": OpenAIProvider("openai"),
            "anthropic": AnthropicProvider(),
            "gemini": GeminiProvider(),
            "kimi": OpenAIProvider("kimi"),
            "glm": OpenAIProvider("glm"),
            "minimax": OpenAIProvider("minimax"),
            "qwen": OpenAIProvider("qwen"),
            "deepseek": OpenAIProvider("deepseek"),
            "step": OpenAIProvider("step"),
        }

    def get_provider(self, provider_name: str | None = None) -> LLMProvider:
        if not provider_name:
            provider_name, _ = config.resolve_model()
        return self._providers.get(provider_name, self._providers["mock"])
