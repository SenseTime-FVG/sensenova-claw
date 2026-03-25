from __future__ import annotations

from copy import deepcopy

from sensenova_claw.adapters.llm.factory import LLMFactory
from sensenova_claw.adapters.llm.providers.anthropic_provider import AnthropicProvider
from sensenova_claw.adapters.llm.providers.gemini_provider import GeminiProvider
from sensenova_claw.adapters.llm.providers.openai_provider import OpenAIProvider
from sensenova_claw.platform.config.config import config


def test_factory_routes_openai_compatible_by_provider_id():
    original = deepcopy(config.data)
    try:
        config.data["llm"]["providers"]["corp-proxy"] = {
            "source_type": "openai-compatible",
            "api_key": "sk-proxy",
            "base_url": "https://proxy.example.com/v1",
            "timeout": 45,
            "max_retries": 2,
        }

        factory = LLMFactory()
        provider = factory.get_provider("corp-proxy")

        assert isinstance(provider, OpenAIProvider)
        assert provider.provider_id == "corp-proxy"
        assert provider.source_type == "openai-compatible"
    finally:
        config.data = original


def test_factory_routes_anthropic_compatible_by_provider_id():
    original = deepcopy(config.data)
    try:
        config.data["llm"]["providers"]["corp-claude"] = {
            "source_type": "anthropic-compatible",
            "api_key": "sk-claude",
            "base_url": "https://anthropic-proxy.example.com",
            "timeout": 50,
            "max_retries": 2,
        }

        factory = LLMFactory()
        provider = factory.get_provider("corp-claude")

        assert isinstance(provider, AnthropicProvider)
        assert provider.provider_id == "corp-claude"
        assert provider.source_type == "anthropic-compatible"
    finally:
        config.data = original


def test_factory_routes_gemini_compatible_by_provider_id():
    original = deepcopy(config.data)
    try:
        config.data["llm"]["providers"]["corp-gemini"] = {
            "source_type": "gemini-compatible",
            "api_key": "sk-gemini",
            "base_url": "https://gemini-proxy.example.com/openai",
            "timeout": 55,
            "max_retries": 2,
        }

        factory = LLMFactory()
        provider = factory.get_provider("corp-gemini")

        assert isinstance(provider, GeminiProvider)
        assert provider.provider_id == "corp-gemini"
        assert provider.source_type == "gemini-compatible"
    finally:
        config.data = original
