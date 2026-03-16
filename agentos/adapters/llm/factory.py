from __future__ import annotations

import os

from agentos.platform.config.config import config
from agentos.adapters.llm.base import LLMProvider
from agentos.adapters.llm.providers.anthropic_provider import AnthropicProvider
from agentos.adapters.llm.providers.gemini_provider import GeminiProvider
from agentos.adapters.llm.providers.mock_provider import MockProvider
from agentos.adapters.llm.providers.openai_provider import OpenAIProvider


class LLMFactory:
    def __init__(self):
        # Always-available mock provider
        providers: dict[str, LLMProvider] = {
            "mock": MockProvider(),
        }

        # Only register real providers when they are actually configured.
        # This avoids startup failures when some API keys are intentionally unset.
        openai_cfg = config.get("llm_providers.openai", {})
        if openai_cfg.get("api_key") or os.getenv("OPENAI_API_KEY"):
            providers["openai"] = OpenAIProvider()

        anthropic_cfg = config.get("llm_providers.anthropic", {})
        if anthropic_cfg.get("api_key") or os.getenv("ANTHROPIC_API_KEY"):
            providers["anthropic"] = AnthropicProvider()

        gemini_cfg = config.get("llm_providers.gemini", {})
        if gemini_cfg.get("api_key") or os.getenv("GEMINI_API_KEY"):
            providers["gemini"] = GeminiProvider()

        self._providers = providers

    def get_provider(self, provider_name: str | None = None) -> LLMProvider:
        name = provider_name or config.get("agent.provider", "mock")
        return self._providers.get(name, self._providers["mock"])
