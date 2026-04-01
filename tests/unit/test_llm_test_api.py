"""LLM 连接测试接口单元测试。"""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

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


def test_normalize_llm_test_error_extracts_max_tokens_hint() -> None:
    normalized = config_api._normalize_llm_test_error(
        "Error code: 400 - InternalError.Algo.InvalidParameter: Range of max_tokens should be [1, 65536]"
    )

    assert normalized["error_hint"] == "max tokens 超限"


def test_normalize_llm_test_error_extracts_max_output_tokens_hint() -> None:
    normalized = config_api._normalize_llm_test_error(
        "Error code: 400 - max_output_tokens is too large: 200000. This model supports at most 8192 output tokens."
    )

    assert normalized["error_hint"] == "max output tokens 超限"


def test_normalize_llm_test_error_extracts_model_limit_max_tokens_hint() -> None:
    normalized = config_api._normalize_llm_test_error(
        'Error code: 400 - {"error": {"code": "400", "message": "{\\"message\\":\\"The maximum tokens you requested exceeds the model limit of 128000\\"}"}}'
    )

    assert normalized["error_hint"] == "max tokens 超限"


def test_normalize_llm_test_error_extracts_context_length_exceeded_max_tokens_hint() -> None:
    normalized = config_api._normalize_llm_test_error(
        """Error code: 400 - {'error': {'message': "This model's maximum context length is 262144 tokens. However, you requested 12800020 tokens (20 in the messages, 12800000 in the completion). Please reduce the length of the messages or completion.", 'type': 'context_length_exceeded'}}"""
    )

    assert normalized["error_hint"] == "max tokens 超限"


def test_normalize_llm_test_error_extracts_invalid_max_tokens_range_hint() -> None:
    normalized = config_api._normalize_llm_test_error(
        "Error code: 400 - {'error': {'message': 'Invalid max_tokens value, the valid range of max_tokens is [1, 8192]', 'type': 'invalid_request_error', 'param': None, 'code': 'invalid_request_error'}}"
    )

    assert normalized["error_hint"] == "max tokens 超限"


def test_normalize_llm_test_error_extracts_gemini_max_output_tokens_range_hint() -> None:
    normalized = config_api._normalize_llm_test_error(
        'Error code: 400 - {\'error\': {\'code\': \'400\', \'message\': \'{ "error": { "code": 400, "message": "Unable to submit request because it has a maxOutputTokens value of 6553600 but the supported range is from 1 (inclusive) to 65537 (exclusive). Update the value and try again.", "status": "INVALID_ARGUMENT" }\\n}\'}}'
    )

    assert normalized["error_hint"] == "max tokens 超限"


def test_test_llm_connection_returns_error_hint_for_max_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_test_openai_compatible(**kwargs):
        raise RuntimeError("Range of max_tokens should be [1, 65536]")

    monkeypatch.setattr(config_api, "_test_openai_compatible", fake_test_openai_compatible)

    app = FastAPI()
    app.include_router(config_api.router)
    client = TestClient(app)

    response = client.post("/api/config/test-llm", json={
        "provider": "openai",
        "api_key": "sk-test",
        "base_url": "https://example.com/v1",
        "model_id": "gpt-4.1-mini",
        "max_tokens": 999999,
        "max_output_tokens": 1024,
    })

    assert response.status_code == 200
    assert response.json() == {
        "success": False,
        "error": "Range of max_tokens should be [1, 65536]",
        "error_hint": "max tokens 超限",
    }
