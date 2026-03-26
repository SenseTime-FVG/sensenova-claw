"""LLM 连接测试接口单元测试。"""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from sensenova_claw.interfaces.http import config_api


@pytest.mark.asyncio
async def test_test_openai_compatible_passes_prompt_and_token_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    class FakeCompletions:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(model=kwargs["model"])

    class FakeAsyncOpenAI:
        def __init__(self, *, api_key: str, base_url: str | None, timeout: int) -> None:
            self.api_key = api_key
            self.base_url = base_url
            self.timeout = timeout
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setitem(sys.modules, "openai", ModuleType("openai"))
    sys.modules["openai"].AsyncOpenAI = FakeAsyncOpenAI

    result = await config_api._test_openai_compatible(
        api_key="sk-test",
        base_url="https://example.com/v1",
        model_id="gpt-4.1-mini",
        max_tokens=4096,
        max_output_tokens=1024,
    )

    assert result == {"model": "gpt-4.1-mini", "message": "连接成功"}
    assert calls == [{
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": "连接测试，回复我'hi'，不要多余的文字"}],
        "max_tokens": 4096,
        "extra_body": {"max_output_tokens": 1024},
    }]


@pytest.mark.asyncio
async def test_test_anthropic_passes_prompt_and_max_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    class FakeMessages:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(model=kwargs["model"])

    class FakeAsyncAnthropic:
        def __init__(self, *, api_key: str, base_url: str | None, timeout: int) -> None:
            self.api_key = api_key
            self.base_url = base_url
            self.timeout = timeout
            self.messages = FakeMessages()

    fake_module = ModuleType("anthropic")
    fake_module.AsyncAnthropic = FakeAsyncAnthropic
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)

    result = await config_api._test_anthropic(
        api_key="sk-ant",
        base_url="https://anthropic.example.com",
        model_id="claude-3-5-haiku",
        max_tokens=2048,
        max_output_tokens=512,
    )

    assert result == {"model": "claude-3-5-haiku", "message": "连接成功"}
    assert calls == [{
        "model": "claude-3-5-haiku",
        "messages": [{"role": "user", "content": "连接测试，回复我'hi'，不要多余的文字"}],
        "max_tokens": 2048,
    }]


@pytest.mark.asyncio
async def test_test_gemini_passes_prompt_and_token_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    class FakeCompletions:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(model=kwargs["model"])

    class FakeAsyncOpenAI:
        def __init__(self, *, api_key: str, base_url: str | None, timeout: int) -> None:
            self.api_key = api_key
            self.base_url = base_url
            self.timeout = timeout
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setitem(sys.modules, "openai", ModuleType("openai"))
    sys.modules["openai"].AsyncOpenAI = FakeAsyncOpenAI

    result = await config_api._test_gemini(
        api_key="sk-gemini",
        base_url="",
        model_id="gemini-2.5-flash",
        max_tokens=8192,
        max_output_tokens=1536,
    )

    assert result == {"model": "gemini-2.5-flash", "message": "连接成功"}
    assert calls == [{
        "model": "gemini-2.5-flash",
        "messages": [{"role": "user", "content": "连接测试，回复我'hi'，不要多余的文字"}],
        "max_tokens": 8192,
        "extra_body": {"max_output_tokens": 1536},
    }]
