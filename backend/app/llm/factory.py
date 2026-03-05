from __future__ import annotations

from app.core.config import config
from app.llm.base import LLMProvider
from app.llm.providers.mock_provider import MockProvider
from app.llm.providers.openai_provider import OpenAIProvider


class LLMFactory:
    def __init__(self):
        self._providers: dict[str, LLMProvider] = {
            "mock": MockProvider(),
            "openai": OpenAIProvider(),
        }

    def get_provider(self, provider_name: str | None = None) -> LLMProvider:
        name = provider_name or config.get("agent.provider", "mock")
        return self._providers.get(name, self._providers["mock"])
