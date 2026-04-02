"""LLMSessionWorker 单元测试 — 使用真实组件，无 mock"""
from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest
import pytest_asyncio

from sensenova_claw.adapters.llm.base import LLMProvider
from sensenova_claw.adapters.llm.factory import LLMFactory
from sensenova_claw.adapters.llm.providers.mock_provider import MockProvider
from sensenova_claw.kernel.events.bus import PublicEventBus, PrivateEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import (
    ERROR_RAISED,
    LLM_CALL_DELTA,
    LLM_CALL_COMPLETED,
    LLM_CALL_REQUESTED,
    LLM_CALL_RESULT,
    LLM_CALL_STARTED,
    NOTIFICATION_SESSION,
    USER_TURN_CANCEL_REQUESTED,
)
from sensenova_claw.kernel.runtime.state import SessionStateStore
from sensenova_claw.kernel.runtime.workers.llm_worker import (
    LLMSessionWorker,
    _extract_unsupported_parameters,
)
from sensenova_claw.platform.config.config import config
from tests.conftest import load_gemini_config, skip_if_gemini_unavailable


# ── 辅助组件 ──────────────────────────────────────────────


class _ErrorProvider(LLMProvider):
    """始终抛异常的 LLM Provider，用于测试错误路径"""

    async def call(self, **kwargs):
        raise RuntimeError("API 超时")


class _SilentTimeoutProvider(LLMProvider):
    """抛出无 message 的 TimeoutError，用于验证错误文案兜底。"""

    async def call(self, **kwargs):
        _ = kwargs
        raise asyncio.TimeoutError()


class _MaxTokensRangeProvider(LLMProvider):
    """模拟 Qwen/DashScope max_tokens 越界报错。"""

    async def call(self, **kwargs):
        _ = kwargs
        raise RuntimeError(
            "Error code: 400 - {'error': {'message': "
            "'<400> InternalError.Algo.InvalidParameter: Range of max_tokens should be [1, 65536]', "
            "'type': 'invalid_request_error', 'code': 'invalid_parameter_error'}}"
        )


class _MiniMaxMaxTokensProvider(LLMProvider):
    """模拟 MiniMax max_tokens 越界报错。"""

    async def call(self, **kwargs):
        _ = kwargs
        raise RuntimeError(
            "Error code: 400 - {'type': 'error', 'error': {'type': 'bad_request_error', "
            "'message': 'invalid params, model[MiniMax-M2.7-highspeed] does not support "
            "max tokens > 196608 (2013)', 'http_code': '400'}}"
        )


class _CloudswayMaxTokensProvider(LLMProvider):
    """模拟 Cloudsway/OpenAI 兼容层的 max_tokens 越界报错。"""

    async def call(self, **kwargs):
        _ = kwargs
        raise RuntimeError(
            'Error code: 400 - {\'error\': {\'code\': \'400\', \'message\': '
            '\'{ "error": { "message": "max_tokens is too large: 8192000. '
            'This model supports at most 128000 completion tokens, whereas you provided 8192000.", '
            '"type": "invalid_request_error", "param": "max_tokens", "code": "invalid_value" }\\n}\'}}'
        )


class _RetryableCloudswayMaxTokensProvider(LLMProvider):
    """首次报 Cloudsway max_tokens 越界，第二次成功。"""

    def __init__(self):
        self.calls: list[dict] = []

    async def call(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            raise RuntimeError(
                'Error code: 400 - {\'error\': {\'code\': \'400\', \'message\': '
                '\'{ "error": { "message": "max_tokens is too large: 8192000. '
                'This model supports at most 128000 completion tokens, whereas you provided 8192000.", '
                '"type": "invalid_request_error", "param": "max_tokens", "code": "invalid_value" }\\n}\'}}'
            )
        return {
            "content": "cloudsway 重试成功",
            "tool_calls": [],
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }


class _GeminiCloudswayMaxTokensProvider(LLMProvider):
    """模拟 Gemini/Cloudsway 的 maxOutputTokens 越界报错。"""

    async def call(self, **kwargs):
        _ = kwargs
        raise RuntimeError(
            'Error code: 400 - {\'error\': {\'code\': \'400\', \'message\': '
            '\'{ "error": { "code": 400, "message": '
            '"Unable to submit request because it has a maxOutputTokens value of 8192000 '
            'but the supported range is from 1 (inclusive) to 65537 (exclusive). '
            'Update the value and try again.", "status": "INVALID_ARGUMENT" }\\n}\'}}'
        )


class _RetryableGeminiCloudswayMaxTokensProvider(LLMProvider):
    """首次报 Gemini/Cloudsway maxOutputTokens 越界，第二次成功。"""

    def __init__(self):
        self.calls: list[dict] = []

    async def call(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            raise RuntimeError(
                'Error code: 400 - {\'error\': {\'code\': \'400\', \'message\': '
                '\'{ "error": { "code": 400, "message": '
                '"Unable to submit request because it has a maxOutputTokens value of 8192000 '
                'but the supported range is from 1 (inclusive) to 65537 (exclusive). '
                'Update the value and try again.", "status": "INVALID_ARGUMENT" }\\n}\'}}'
            )
        return {
            "content": "gemini cloudsway 重试成功",
            "tool_calls": [],
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }


class _RetryableConflictingSamplingProvider(LLMProvider):
    """首次报 temperature/top_p 互斥，第二次成功。"""

    def __init__(self):
        self.calls: list[dict] = []

    async def call(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            raise RuntimeError(
                'Error code: 400 - {\'error\': {\'code\': \'400\', \'message\': '
                '\'{"message":"temperature and top_p cannot both be specified for this model. '
                'Please use only one."}\'}}'
            )
        return {
            "content": "冲突参数重试成功",
            "tool_calls": [],
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }


class _RetryableMaxTokensProvider(LLMProvider):
    """首次报 max_tokens 越界，第二次成功。"""

    def __init__(self):
        self.calls: list[dict] = []

    async def call(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            raise RuntimeError(
                "Error code: 400 - {'error': {'message': "
                "'<400> InternalError.Algo.InvalidParameter: Range of max_tokens should be [1, 65536]', "
                "'type': 'invalid_request_error', 'code': 'invalid_parameter_error'}}"
            )
        return {
            "content": "重试成功",
            "tool_calls": [],
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }


class _SuccessProvider(LLMProvider):
    """始终成功的 Provider。"""

    def __init__(self, content: str):
        self.content = content
        self.calls: list[dict] = []

    async def call(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "content": self.content,
            "tool_calls": [],
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }


class _SlowStreamingProvider(LLMProvider):
    """逐段输出的流式 Provider，用于验证取消时能打断在途流。"""

    def __init__(self):
        self.calls: list[dict] = []

    async def call(self, **kwargs):
        raise AssertionError("streaming test should not call non-stream path")

    async def stream_call(self, **kwargs):
        self.calls.append(kwargs)
        for index in range(1000):
            await asyncio.sleep(0.05)
            yield {"type": "delta", "content": f"chunk-{index}"}
        yield {
            "type": "finish",
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "tool_calls": [],
        }


class _RetryableThenErrorProvider(LLMProvider):
    """先触发 max_tokens 重试，再次调用仍失败。"""

    def __init__(self):
        self.calls: list[dict] = []

    async def call(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            raise RuntimeError(
                "Error code: 400 - {'error': {'message': "
                "'<400> InternalError.Algo.InvalidParameter: Range of max_tokens should be [1, 65536]', "
                "'type': 'invalid_request_error', 'code': 'invalid_parameter_error'}}"
            )
        raise RuntimeError("第二次调用仍失败")


class _RetryableUnknownParamsProvider(LLMProvider):
    """首次返回未知参数错误，移除后重试成功。"""

    def __init__(self):
        self.calls: list[dict] = []

    async def call(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            raise RuntimeError(
                'Error code: 400 - {"error": {"message": "Unknown parameters: [\'top_k\', \'foo\']."}}'
            )
        return {
            "content": "参数剔除后成功",
            "tool_calls": [],
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }


class _ExhaustUnknownParamsProvider(LLMProvider):
    """连续返回未知参数错误，直到超过自动重试上限。"""

    def __init__(self):
        self.calls: list[dict] = []
        self._params = ["top_k", "foo", "bar", "baz"]

    async def call(self, **kwargs):
        self.calls.append(kwargs)
        current_index = len(self.calls) - 1
        raise RuntimeError(
            f'Error code: 400 - {{"error": {{"message": "Unknown parameter: \'{self._params[current_index]}\'."}}}}'
        )


class _SimpleLLMRuntime:
    """轻量级 LLMRuntime 替身，持有真实 LLMFactory"""

    def __init__(self, factory: LLMFactory, state_store: SessionStateStore | None = None):
        self.factory = factory
        self.state_store = state_store


# ── Fixtures ─────────────────────────────────────────────


@pytest.fixture
def public_bus():
    return PublicEventBus()


@pytest.fixture
def private_bus(public_bus):
    return PrivateEventBus("s1", public_bus)


@pytest.fixture
def factory():
    return LLMFactory()


@pytest.fixture
def state_store():
    return SessionStateStore()


@pytest.fixture
def runtime(factory, state_store):
    return _SimpleLLMRuntime(factory, state_store)


def _make_llm_event(provider: str, model: str, messages: list[dict],
                     llm_call_id: str = "llm_1", tools: list | None = None) -> EventEnvelope:
    """构造 LLM_CALL_REQUESTED 事件的辅助函数。"""
    payload = {
        "llm_call_id": llm_call_id,
        "provider": provider,
        "model": model,
        "messages": messages,
    }
    if tools is not None:
        payload["tools"] = tools
    return EventEnvelope(
        type=LLM_CALL_REQUESTED,
        session_id="s1",
        turn_id="t1",
        payload=payload,
    )


def _provider_model(provider_name: str) -> tuple[str, str]:
    """根据 provider_name 返回 (provider, model)。"""
    if provider_name == "mock":
        return "mock", "mock-agent-v1"
    cfg = load_gemini_config()
    return "gemini", cfg["default_model"] if cfg else ""


async def _collect_from_bus(public_bus, count, timeout=5.0):
    """从公共总线收集指定数量的事件"""
    collected = []
    done = asyncio.Event()

    async def collector():
        async for evt in public_bus.subscribe():
            collected.append(evt)
            if len(collected) >= count:
                done.set()
                break

    task = asyncio.create_task(collector())
    await asyncio.sleep(0.01)  # 等待订阅完成
    return collected, done, task


# ── _handle 路由测试 ──────────────────────────────────────


class TestLLMWorkerHandle:
    """_handle 路由测试"""

    async def test_ignores_non_llm_requested_events(self, private_bus, runtime):
        worker = LLMSessionWorker("s1", private_bus, runtime)
        event = EventEnvelope(type="other.event", session_id="s1")
        await worker._handle(event)

    async def test_applies_default_sampling_when_event_omits_it(self, private_bus, runtime, monkeypatch):
        provider = _SuccessProvider("ok")
        runtime.factory.get_provider = lambda provider_name="mock": provider
        worker = LLMSessionWorker("s1", private_bus, runtime)
        event = _make_llm_event("mock", "mock-agent-v1", [{"role": "user", "content": "hi"}])

        original_temperature = config.get("agent.temperature")
        original_extra_body = config.get("agent.extra_body")
        config.set("agent.temperature", 1.0)
        config.set("agent.extra_body", {"top_p": 0.95, "top_k": 20})
        try:
            await worker._handle_llm_requested(event)
        finally:
            config.set("agent.temperature", original_temperature)
            config.set("agent.extra_body", original_extra_body)

        assert provider.calls[0]["temperature"] == 1.0
        assert provider.calls[0]["extra_body"] == {"top_p": 0.95, "top_k": 20}
        # 不抛异常即可

    async def test_explicit_empty_model_does_not_fallback_to_default_model(self, private_bus, runtime):
        original = deepcopy(config.data)
        try:
            config.data["llm"]["default_model"] = "gpt-5.4"
            provider = _SuccessProvider("ok")
            runtime.factory.get_provider = lambda provider_name="mock": provider
            worker = LLMSessionWorker("s1", private_bus, runtime)
            event = _make_llm_event("openai", "", [{"role": "user", "content": "hi"}])
            event.payload["stream"] = False

            await worker._handle_llm_requested(event)

            assert provider.calls
            assert provider.calls[0]["model"] == ""
        finally:
            config.data = original

    @pytest.mark.parametrize("provider_name", ["mock", "gemini"])
    async def test_routes_llm_requested(self, private_bus, public_bus, runtime, provider_name):
        skip_if_gemini_unavailable(provider_name)
        provider, model = _provider_model(provider_name)
        timeout = 30 if provider_name == "gemini" else 5

        worker = LLMSessionWorker("s1", private_bus, runtime)
        collected, done, task = await _collect_from_bus(public_bus, 3)

        event = _make_llm_event(provider, model, [{"role": "user", "content": "hello"}])
        await worker._handle(event)
        await asyncio.wait_for(done.wait(), timeout=timeout)
        task.cancel()

        types = [e.type for e in collected]
        assert LLM_CALL_STARTED in types
        assert LLM_CALL_RESULT in types
        assert LLM_CALL_COMPLETED in types


# ── LLM 调用成功路径 ─────────────────────────────────────


class TestLLMWorkerSuccess:
    """LLM 调用成功路径"""

    @pytest.mark.parametrize("provider_name", ["mock", "gemini"])
    async def test_publishes_correct_event_sequence(self, private_bus, public_bus, runtime, provider_name):
        skip_if_gemini_unavailable(provider_name)
        provider, model = _provider_model(provider_name)
        timeout = 30 if provider_name == "gemini" else 5

        worker = LLMSessionWorker("s1", private_bus, runtime)
        collected, done, task = await _collect_from_bus(public_bus, 3)

        event = _make_llm_event(
            provider, model,
            [{"role": "user", "content": "hello"}],
            llm_call_id="llm_abc",
        )
        await worker._handle(event)
        await asyncio.wait_for(done.wait(), timeout=timeout)
        task.cancel()

        assert collected[0].type == LLM_CALL_STARTED
        assert collected[0].trace_id == "llm_abc"
        result_event = collected[1]
        assert result_event.type == LLM_CALL_RESULT
        assert result_event.payload["response"]["content"]

        if provider_name == "mock":
            # mock provider 固定 finish_reason
            assert result_event.payload["finish_reason"] == "stop"

        assert collected[2].type == LLM_CALL_COMPLETED

    async def test_passes_tool_calls_through(self, private_bus, public_bus, runtime):
        """请求包含英超冠亚军关键词时，mock provider 返回 tool_calls"""
        worker = LLMSessionWorker("s1", private_bus, runtime)
        collected, done, task = await _collect_from_bus(public_bus, 3)

        event = _make_llm_event(
            "mock", "mock-agent-v1",
            [{"role": "user", "content": "英超冠亚军是谁"}],
            tools=[{"name": "serper_search"}],
        )
        await worker._handle(event)
        await asyncio.wait_for(done.wait(), timeout=5)
        task.cancel()

        result_event = [e for e in collected if e.type == LLM_CALL_RESULT][0]
        tc = result_event.payload["response"]["tool_calls"]
        assert len(tc) > 0
        assert tc[0]["name"] == "serper_search"


# ── LLM 调用失败路径（仅 mock，测试错误处理逻辑）──────────


class TestLLMWorkerError:
    """LLM 调用失败路径"""

    async def test_error_publishes_error_and_fallback_result(self, private_bus, public_bus):
        original = deepcopy(config.data)
        try:
            config.data["llm"]["default_model"] = "mock"
            factory = LLMFactory()
            factory._providers["mock"] = _ErrorProvider()
            runtime = _SimpleLLMRuntime(factory)
            worker = LLMSessionWorker("s1", private_bus, runtime)

            collected, done, task = await _collect_from_bus(public_bus, 4)

            event = _make_llm_event("mock", "mock-agent-v1", [{"role": "user", "content": "test"}])
            await worker._handle(event)
            await asyncio.wait_for(done.wait(), timeout=5)
            task.cancel()

            types = [e.type for e in collected]
            assert types[0] == LLM_CALL_STARTED
            assert ERROR_RAISED in types
            err = [e for e in collected if e.type == ERROR_RAISED][0]
            assert "API 超时" in err.payload["error_message"]
            fallback = [e for e in collected if e.type == LLM_CALL_RESULT][0]
            assert "LLM调用失败" in fallback.payload["response"]["content"]
            assert fallback.payload["finish_reason"] == "error"
            assert LLM_CALL_COMPLETED in types
        finally:
            config.data = original

    async def test_timeout_without_message_uses_exception_type(self, private_bus, public_bus):
        original = deepcopy(config.data)
        try:
            config.data["llm"]["default_model"] = "mock"
            factory = LLMFactory()
            factory._providers["mock"] = _SilentTimeoutProvider()
            runtime = _SimpleLLMRuntime(factory)
            worker = LLMSessionWorker("s1", private_bus, runtime)

            collected, done, task = await _collect_from_bus(public_bus, 4)

            event = _make_llm_event("mock", "mock-agent-v1", [{"role": "user", "content": "test"}])
            await worker._handle(event)
            await asyncio.wait_for(done.wait(), timeout=5)
            task.cancel()

            err = [e for e in collected if e.type == ERROR_RAISED][0]
            fallback = [e for e in collected if e.type == LLM_CALL_RESULT][0]
            assert err.payload["error_message"] == "TimeoutError"
            assert "TimeoutError" in fallback.payload["response"]["content"]
        finally:
            config.data = original

    async def test_explicit_provider_unavailable_does_not_silently_fallback_to_mock(
        self, private_bus, public_bus
    ):
        """显式请求 qwen 时，应提示并回退到 mock。"""
        original = deepcopy(config.data)
        try:
            config.data["llm"]["default_model"] = "mock"
            factory = LLMFactory()
            factory._providers.pop("qwen", None)
            factory._lazy.pop("qwen", None)
            factory._PROVIDER_FACTORIES.pop("qwen", None)

            runtime = _SimpleLLMRuntime(factory)
            worker = LLMSessionWorker("s1", private_bus, runtime)
            collected, done, task = await _collect_from_bus(public_bus, 4)

            event = _make_llm_event("qwen", "qwen3.5-plus", [{"role": "user", "content": "你好"}])
            await worker._handle(event)
            await asyncio.wait_for(done.wait(), timeout=5)
            task.cancel()

            types = [e.type for e in collected]
            assert ERROR_RAISED not in types
            notices = [e for e in collected if e.type == NOTIFICATION_SESSION]
            assert len(notices) == 2
            assert "qwen:qwen3.5-plus" in notices[0].payload["body"]
            assert "mock:mock-agent-v1" in notices[1].payload["body"]
            fallback = [e for e in collected if e.type == LLM_CALL_RESULT][0]
            assert "当前没有可用的 LLM" in fallback.payload["response"]["content"]
            assert fallback.payload["finish_reason"] == "stop"
        finally:
            config.data = original

    async def test_max_tokens_out_of_range_is_normalized_for_user(self, private_bus, public_bus):
        original = deepcopy(config.data)
        try:
            config.data["llm"]["default_model"] = "mock"
            factory = LLMFactory()
            factory._providers["qwen"] = _MaxTokensRangeProvider()
            runtime = _SimpleLLMRuntime(factory)
            worker = LLMSessionWorker("s1", private_bus, runtime)

            collected, done, task = await _collect_from_bus(public_bus, 4)

            event = _make_llm_event("qwen", "qwen3.5-plus", [{"role": "user", "content": "你好"}])
            await worker._handle(event)
            await asyncio.wait_for(done.wait(), timeout=5)
            task.cancel()

            types = [e.type for e in collected]
            assert ERROR_RAISED not in types
            notices = [e for e in collected if e.type == NOTIFICATION_SESSION]
            assert len(notices) == 2
            assert "qwen:qwen3.5-plus 调用失败" in notices[0].payload["body"]
            assert "65536" in notices[0].payload["body"]
            assert "mock:mock-agent-v1" in notices[1].payload["body"]
        finally:
            config.data = original

    async def test_minimax_max_tokens_out_of_range_is_normalized_for_user(self, private_bus, public_bus):
        original = deepcopy(config.data)
        try:
            config.data["llm"]["default_model"] = "mock"
            factory = LLMFactory()
            factory._providers["minimax"] = _MiniMaxMaxTokensProvider()
            runtime = _SimpleLLMRuntime(factory)
            worker = LLMSessionWorker("s1", private_bus, runtime)

            collected, done, task = await _collect_from_bus(public_bus, 4)

            event = _make_llm_event("minimax", "MiniMax-M2.7-highspeed", [{"role": "user", "content": "你好"}])
            await worker._handle(event)
            await asyncio.wait_for(done.wait(), timeout=5)
            task.cancel()

            types = [e.type for e in collected]
            assert ERROR_RAISED not in types
            notices = [e for e in collected if e.type == NOTIFICATION_SESSION]
            assert len(notices) == 2
            assert "minimax:MiniMax-M2.7-highspeed 调用失败" in notices[0].payload["body"]
            assert "196608" in notices[0].payload["body"]
            assert "mock:mock-agent-v1" in notices[1].payload["body"]
        finally:
            config.data = original

    async def test_cloudsway_max_tokens_out_of_range_is_normalized_for_user(self, private_bus, public_bus):
        original = deepcopy(config.data)
        try:
            config.data["llm"]["default_model"] = "mock"
            factory = LLMFactory()
            factory._providers["openai-cloudsway"] = _CloudswayMaxTokensProvider()
            runtime = _SimpleLLMRuntime(factory)
            worker = LLMSessionWorker("s1", private_bus, runtime)

            collected, done, task = await _collect_from_bus(public_bus, 4)

            event = _make_llm_event("openai-cloudsway", "MaaS_GP_5.4_20260305", [{"role": "user", "content": "你好"}])
            await worker._handle(event)
            await asyncio.wait_for(done.wait(), timeout=5)
            task.cancel()

            types = [e.type for e in collected]
            assert ERROR_RAISED not in types
            notices = [e for e in collected if e.type == NOTIFICATION_SESSION]
            assert len(notices) == 2
            assert "openai-cloudsway:MaaS_GP_5.4_20260305 调用失败" in notices[0].payload["body"]
            assert "128000" in notices[0].payload["body"]
            assert "mock:mock-agent-v1" in notices[1].payload["body"]
        finally:
            config.data = original

    async def test_gemini_cloudsway_max_tokens_out_of_range_is_normalized_for_user(self, private_bus, public_bus):
        original = deepcopy(config.data)
        try:
            config.data["llm"]["default_model"] = "mock"
            factory = LLMFactory()
            factory._providers["gemini"] = _GeminiCloudswayMaxTokensProvider()
            runtime = _SimpleLLMRuntime(factory)
            worker = LLMSessionWorker("s1", private_bus, runtime)

            collected, done, task = await _collect_from_bus(public_bus, 4)

            event = _make_llm_event("gemini", "MaaS_Ge_3.1_pro_preview_20260219", [{"role": "user", "content": "你好"}])
            await worker._handle(event)
            await asyncio.wait_for(done.wait(), timeout=5)
            task.cancel()

            types = [e.type for e in collected]
            assert ERROR_RAISED not in types
            notices = [e for e in collected if e.type == NOTIFICATION_SESSION]
            assert len(notices) == 2
            assert "gemini:MaaS_Ge_3.1_pro_preview_20260219 调用失败" in notices[0].payload["body"]
            assert "65536" in notices[0].payload["body"]
            assert "mock:mock-agent-v1" in notices[1].payload["body"]
        finally:
            config.data = original

    async def test_max_tokens_out_of_range_retries_once_after_notification(self, private_bus, public_bus):
        provider = _RetryableMaxTokensProvider()
        factory = LLMFactory()
        factory._providers["qwen"] = provider
        runtime = _SimpleLLMRuntime(factory)
        worker = LLMSessionWorker("s1", private_bus, runtime)

        collected, done, task = await _collect_from_bus(public_bus, 4)

        event = EventEnvelope(
            type=LLM_CALL_REQUESTED,
            session_id="s1",
            turn_id="t1",
            payload={
                "llm_call_id": "llm_retry",
                "provider": "qwen",
                "model": "qwen3.5-plus",
                "messages": [{"role": "user", "content": "你好"}],
                "max_tokens": 1000000,
            },
        )
        await worker._handle(event)
        await asyncio.wait_for(done.wait(), timeout=5)
        task.cancel()

        types = [e.type for e in collected]
        assert ERROR_RAISED not in types
        assert NOTIFICATION_SESSION in types
        notification = [e for e in collected if e.type == NOTIFICATION_SESSION][0]
        assert "已自动调整为 65536 并重试" in notification.payload["body"]
        result = [e for e in collected if e.type == LLM_CALL_RESULT][0]
        assert result.payload["response"]["content"] == "重试成功"
        assert provider.calls[0]["max_tokens"] == 1000000
        assert provider.calls[1]["max_tokens"] == 65536

    async def test_cloudsway_max_tokens_out_of_range_retries_once_after_notification(self, private_bus, public_bus):
        provider = _RetryableCloudswayMaxTokensProvider()
        factory = LLMFactory()
        factory._providers["openai-cloudsway"] = provider
        runtime = _SimpleLLMRuntime(factory)
        worker = LLMSessionWorker("s1", private_bus, runtime)

        collected, done, task = await _collect_from_bus(public_bus, 4)

        event = EventEnvelope(
            type=LLM_CALL_REQUESTED,
            session_id="s1",
            turn_id="t1",
            payload={
                "llm_call_id": "llm_retry_cloudsway",
                "provider": "openai-cloudsway",
                "model": "MaaS_GP_5.4_20260305",
                "messages": [{"role": "user", "content": "你好"}],
                "max_tokens": 8192000,
                "stream": False,
            },
        )
        await worker._handle(event)
        await asyncio.wait_for(done.wait(), timeout=5)
        task.cancel()

        types = [e.type for e in collected]
        assert ERROR_RAISED not in types
        assert NOTIFICATION_SESSION in types
        notification = [e for e in collected if e.type == NOTIFICATION_SESSION][0]
        assert "已自动调整为 128000 并重试" in notification.payload["body"]
        result = [e for e in collected if e.type == LLM_CALL_RESULT][0]
        assert result.payload["response"]["content"] == "cloudsway 重试成功"
        assert provider.calls[0]["max_tokens"] == 8192000
        assert provider.calls[1]["max_tokens"] == 128000

    async def test_gemini_cloudsway_max_tokens_out_of_range_retries_once_after_notification(self, private_bus, public_bus):
        provider = _RetryableGeminiCloudswayMaxTokensProvider()
        factory = LLMFactory()
        factory._providers["gemini"] = provider
        runtime = _SimpleLLMRuntime(factory)
        worker = LLMSessionWorker("s1", private_bus, runtime)

        collected, done, task = await _collect_from_bus(public_bus, 4)

        event = EventEnvelope(
            type=LLM_CALL_REQUESTED,
            session_id="s1",
            turn_id="t1",
            payload={
                "llm_call_id": "llm_retry_gemini_cloudsway",
                "provider": "gemini",
                "model": "MaaS_Ge_3.1_pro_preview_20260219",
                "messages": [{"role": "user", "content": "你好"}],
                "max_tokens": 8192000,
                "stream": False,
            },
        )
        await worker._handle(event)
        await asyncio.wait_for(done.wait(), timeout=5)
        task.cancel()

        types = [e.type for e in collected]
        assert ERROR_RAISED not in types
        assert NOTIFICATION_SESSION in types
        notification = [e for e in collected if e.type == NOTIFICATION_SESSION][0]
        assert "已自动调整为 65536 并重试" in notification.payload["body"]
        result = [e for e in collected if e.type == LLM_CALL_RESULT][0]
        assert result.payload["response"]["content"] == "gemini cloudsway 重试成功"
        assert provider.calls[0]["max_tokens"] == 8192000
        assert provider.calls[1]["max_tokens"] == 65536

    async def test_conflicting_sampling_parameters_retry_keeps_first_parameter(self, private_bus, public_bus):
        provider = _RetryableConflictingSamplingProvider()
        factory = LLMFactory()
        factory._providers["anthropic-cloudsway"] = provider
        runtime = _SimpleLLMRuntime(factory)
        worker = LLMSessionWorker("s1", private_bus, runtime)

        collected, done, task = await _collect_from_bus(public_bus, 4)

        event = EventEnvelope(
            type=LLM_CALL_REQUESTED,
            session_id="s1",
            turn_id="t1",
            payload={
                "llm_call_id": "llm_retry_conflicting_sampling",
                "provider": "anthropic-cloudsway",
                "model": "MaaS_Cl_Sonnet_4.6_20260217",
                "messages": [{"role": "user", "content": "你好"}],
                "extra_body": {"top_p": 0.95},
                "stream": False,
            },
        )
        await worker._handle(event)
        await asyncio.wait_for(done.wait(), timeout=5)
        task.cancel()

        types = [e.type for e in collected]
        assert ERROR_RAISED not in types
        notification = [e for e in collected if e.type == NOTIFICATION_SESSION][0]
        assert "temperature, top_p 互斥" in notification.payload["body"]
        assert "仅保留 temperature" in notification.payload["body"]
        result = [e for e in collected if e.type == LLM_CALL_RESULT][0]
        assert result.payload["response"]["content"] == "冲突参数重试成功"
        assert provider.calls[0]["temperature"] == 1.0
        assert provider.calls[0]["extra_body"] == {"top_p": 0.95, "top_k": 20}
        assert provider.calls[1]["temperature"] == 1.0
        assert provider.calls[1]["extra_body"] == {"top_p": None, "top_k": 20}

    async def test_unknown_parameters_are_removed_in_one_retry(self, private_bus, public_bus):
        provider = _RetryableUnknownParamsProvider()
        factory = LLMFactory()
        factory._providers["qwen"] = provider
        runtime = _SimpleLLMRuntime(factory)
        worker = LLMSessionWorker("s1", private_bus, runtime)

        collected, done, task = await _collect_from_bus(public_bus, 4)

        event = EventEnvelope(
            type=LLM_CALL_REQUESTED,
            session_id="s1",
            turn_id="t1",
            payload={
                "llm_call_id": "llm_unknown_param_retry",
                "provider": "qwen",
                "model": "qwen3.5-plus",
                "messages": [{"role": "user", "content": "你好"}],
                "extra_body": {"top_p": 0.95, "top_k": 20, "foo": 1, "bar": 2},
                "stream": False,
            },
        )
        await worker._handle(event)
        await asyncio.wait_for(done.wait(), timeout=5)
        task.cancel()

        notices = [e for e in collected if e.type == NOTIFICATION_SESSION]
        assert len(notices) == 1
        assert "top_k, foo" in notices[0].payload["body"]
        result = [e for e in collected if e.type == LLM_CALL_RESULT][0]
        assert result.payload["response"]["content"] == "参数剔除后成功"
        assert provider.calls[0]["extra_body"] == {"top_p": 0.95, "top_k": 20, "foo": 1, "bar": 2}
        assert provider.calls[1]["extra_body"] == {"top_p": 0.95, "top_k": None, "foo": None, "bar": 2}

    async def test_unknown_parameter_retry_stops_after_three_rounds(self, private_bus, public_bus):
        original = deepcopy(config.data)
        try:
            config.data["llm"]["default_model"] = "mock"
            provider = _ExhaustUnknownParamsProvider()
            factory = LLMFactory()
            factory._providers["qwen"] = provider
            runtime = _SimpleLLMRuntime(factory)
            worker = LLMSessionWorker("s1", private_bus, runtime)

            collected, done, task = await _collect_from_bus(public_bus, 8)

            event = EventEnvelope(
                type=LLM_CALL_REQUESTED,
                session_id="s1",
                turn_id="t1",
                payload={
                    "llm_call_id": "llm_unknown_param_limit",
                    "provider": "qwen",
                    "model": "qwen3.5-plus",
                    "messages": [{"role": "user", "content": "你好"}],
                    "extra_body": {"top_k": 20, "foo": 1, "bar": 2, "baz": 3},
                    "stream": False,
                },
            )
            await worker._handle(event)
            await asyncio.wait_for(done.wait(), timeout=5)
            task.cancel()

            notices = [e for e in collected if e.type == NOTIFICATION_SESSION]
            assert len(notices) == 5
            assert "top_k" in notices[0].payload["body"]
            assert "foo" in notices[1].payload["body"]
            assert "bar" in notices[2].payload["body"]
            assert "qwen:qwen3.5-plus 调用失败" in notices[3].payload["body"]
            assert "mock:mock-agent-v1" in notices[4].payload["body"]
            result = [e for e in collected if e.type == LLM_CALL_RESULT][0]
            assert "当前没有可用的 LLM" in result.payload["response"]["content"]
            assert provider.calls[0]["extra_body"] == {"top_p": 0.95, "top_k": 20, "foo": 1, "bar": 2, "baz": 3}
            assert provider.calls[1]["extra_body"] == {"top_p": 0.95, "top_k": None, "foo": 1, "bar": 2, "baz": 3}
            assert provider.calls[2]["extra_body"] == {"top_p": 0.95, "top_k": None, "foo": None, "bar": 2, "baz": 3}
            assert provider.calls[3]["extra_body"] == {"top_p": 0.95, "top_k": None, "foo": None, "bar": None, "baz": 3}
        finally:
            config.data = original


def test_extract_unsupported_parameters_from_openai_nested_error_message():
    message = (
        "Error code: 400 - {'error': {'code': '400', 'message': "
        '\'{ "error": { "message": "Unknown parameter: \\\'top_k\\\'.", '
        '"type": "invalid_request_error", "param": "top_k", "code": "unknown_parameter" }\\n}\'}}'
    )

    assert _extract_unsupported_parameters(message) == ["top_k"]


def test_extract_conflicting_parameters_with_backticks():
    message = (
        'Error code: 400 - {\'error\': {\'code\': \'400\', \'message\': '
        '\'{"message":"`temperature` and `top_p` cannot both be specified for this model. '
        'Please use only one."}\'}}'
    )

    from sensenova_claw.kernel.runtime.workers.llm_worker import _extract_conflicting_parameters

    assert _extract_conflicting_parameters(message) == ["temperature", "top_p"]

    async def test_provider_failure_falls_back_to_default_model_with_notification(self, private_bus, public_bus):
        original = deepcopy(config.data)
        try:
            config.data["llm"]["default_model"] = "gemini-pro"
            config.data["llm"]["models"]["gemini-pro"] = {
                "provider": "gemini",
                "model_id": "gemini-2.5-pro",
            }

            factory = LLMFactory()
            factory._providers["qwen"] = _ErrorProvider()
            gemini = _SuccessProvider("default fallback success")
            factory._providers["gemini"] = gemini
            runtime = _SimpleLLMRuntime(factory)
            worker = LLMSessionWorker("s1", private_bus, runtime)

            collected, done, task = await _collect_from_bus(public_bus, 5)

            event = _make_llm_event("qwen", "qwen3.5-plus", [{"role": "user", "content": "test"}])
            await worker._handle(event)
            await asyncio.wait_for(done.wait(), timeout=5)
            task.cancel()

            types = [e.type for e in collected]
            assert ERROR_RAISED not in types
            notices = [e for e in collected if e.type == NOTIFICATION_SESSION]
            assert len(notices) == 2
            assert "qwen:qwen3.5-plus" in notices[0].payload["body"]
            assert "gemini:gemini-2.5-pro" in notices[1].payload["body"]
            result = [e for e in collected if e.type == LLM_CALL_RESULT][0]
            assert result.payload["response"]["content"] == "default fallback success"
            assert gemini.calls[0]["model"] == "gemini-2.5-pro"
        finally:
            config.data = original

    async def test_default_model_failure_falls_back_to_first_available_llm_before_mock(
        self, private_bus, public_bus
    ):
        original = deepcopy(config.data)
        try:
            config.data["llm"]["default_model"] = "gemini-pro"
            config.data["llm"]["models"] = {
                "mock": {
                    "provider": "mock",
                    "model_id": "mock-agent-v1",
                },
                "gemini-pro": {
                    "provider": "gemini",
                    "model_id": "gemini-2.5-pro",
                },
                "gpt-5.4": {
                    "provider": "openai",
                    "model_id": "gpt-5.4",
                },
            }
            config.data["llm"]["providers"]["openai"]["api_key"] = "sk-test-openai"

            factory = LLMFactory()
            factory._providers["qwen"] = _ErrorProvider()
            factory._providers["gemini"] = _ErrorProvider()
            openai = _SuccessProvider("third hop success")
            factory._providers["openai"] = openai
            runtime = _SimpleLLMRuntime(factory)
            worker = LLMSessionWorker("s1", private_bus, runtime)

            collected, done, task = await _collect_from_bus(public_bus, 7)

            event = _make_llm_event("qwen", "qwen3.5-plus", [{"role": "user", "content": "test"}])
            await worker._handle(event)
            await asyncio.wait_for(done.wait(), timeout=5)
            task.cancel()

            types = [e.type for e in collected]
            assert ERROR_RAISED not in types
            notices = [e for e in collected if e.type == NOTIFICATION_SESSION]
            assert len(notices) == 4
            assert "qwen:qwen3.5-plus" in notices[0].payload["body"]
            assert "gemini:gemini-2.5-pro" in notices[1].payload["body"]
            assert "gemini:gemini-2.5-pro" in notices[2].payload["body"]
            assert "openai:gpt-5.4" in notices[3].payload["body"]
            result = [e for e in collected if e.type == LLM_CALL_RESULT][0]
            assert result.payload["response"]["content"] == "third hop success"
            assert openai.calls[0]["model"] == "gpt-5.4"
        finally:
            config.data = original

    async def test_default_model_failure_falls_back_to_mock_with_notification(self, private_bus, public_bus):
        original = deepcopy(config.data)
        try:
            config.data["llm"]["default_model"] = "gemini-pro"
            config.data["llm"]["models"]["gemini-pro"] = {
                "provider": "gemini",
                "model_id": "gemini-2.5-pro",
            }

            factory = LLMFactory()
            factory._providers["qwen"] = _ErrorProvider()
            factory._providers["gemini"] = _ErrorProvider()
            runtime = _SimpleLLMRuntime(factory)
            worker = LLMSessionWorker("s1", private_bus, runtime)

            collected, done, task = await _collect_from_bus(public_bus, 7)

            event = _make_llm_event("qwen", "qwen3.5-plus", [{"role": "user", "content": "test"}])
            await worker._handle(event)
            await asyncio.wait_for(done.wait(), timeout=5)
            task.cancel()

            types = [e.type for e in collected]
            assert ERROR_RAISED not in types
            notices = [e for e in collected if e.type == NOTIFICATION_SESSION]
            assert len(notices) == 4
            assert "qwen:qwen3.5-plus" in notices[0].payload["body"]
            assert "gemini:gemini-2.5-pro" in notices[1].payload["body"]
            assert "gemini:gemini-2.5-pro" in notices[2].payload["body"]
            assert "mock:mock-agent-v1" in notices[3].payload["body"]
            result = [e for e in collected if e.type == LLM_CALL_RESULT][0]
            assert "当前没有可用的 LLM" in result.payload["response"]["content"]
            assert result.payload["finish_reason"] == "stop"
        finally:
            config.data = original

    async def test_max_tokens_retry_failure_then_falls_back(self, private_bus, public_bus):
        original = deepcopy(config.data)
        try:
            config.data["llm"]["default_model"] = "gemini-pro"
            config.data["llm"]["models"]["gemini-pro"] = {
                "provider": "gemini",
                "model_id": "gemini-2.5-pro",
            }

            qwen = _RetryableThenErrorProvider()
            gemini = _SuccessProvider("fallback after retry failure")
            factory = LLMFactory()
            factory._providers["qwen"] = qwen
            factory._providers["gemini"] = gemini
            runtime = _SimpleLLMRuntime(factory)
            worker = LLMSessionWorker("s1", private_bus, runtime)

            collected, done, task = await _collect_from_bus(public_bus, 6)

            event = EventEnvelope(
                type=LLM_CALL_REQUESTED,
                session_id="s1",
                turn_id="t1",
                payload={
                    "llm_call_id": "llm_retry_fallback",
                    "provider": "qwen",
                    "model": "qwen3.5-plus",
                    "messages": [{"role": "user", "content": "你好"}],
                    "max_tokens": 1000000,
                },
            )
            await worker._handle(event)
            await asyncio.wait_for(done.wait(), timeout=5)
            task.cancel()

            notices = [e for e in collected if e.type == NOTIFICATION_SESSION]
            assert len(notices) == 3
            assert "qwen:qwen3.5-plus 的 max_tokens 超出模型上限" in notices[0].payload["body"]
            assert "已自动调整为 65536 并重试" in notices[0].payload["body"]
            assert "qwen:qwen3.5-plus" in notices[1].payload["body"]
            assert "gemini:gemini-2.5-pro" not in notices[1].payload["body"]
            assert "gemini:gemini-2.5-pro" in notices[2].payload["body"]
            result = [e for e in collected if e.type == LLM_CALL_RESULT][0]
            assert result.payload["response"]["content"] == "fallback after retry failure"
            assert qwen.calls[0]["max_tokens"] == 1000000
            assert qwen.calls[1]["max_tokens"] == 65536
        finally:
            config.data = original


# ── 配置回退测试 ──────────────────────────────────────────


class TestLLMWorkerConfigFallback:
    """不传 provider/model 时使用全局配置默认值"""

    async def test_uses_config_defaults_when_payload_empty(self, private_bus, public_bus, runtime):
        original = deepcopy(config.data)
        try:
            config.data["llm"]["default_model"] = "mock"
            worker = LLMSessionWorker("s1", private_bus, runtime)
            collected, done, task = await _collect_from_bus(public_bus, 3)

            event = EventEnvelope(
                type=LLM_CALL_REQUESTED,
                session_id="s1",
                turn_id="t1",
                payload={
                    "llm_call_id": "llm_1",
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )
            await worker._handle(event)
            await asyncio.wait_for(done.wait(), timeout=5)
            task.cancel()

            result_events = [e for e in collected if e.type == LLM_CALL_RESULT]
            assert len(result_events) == 1
            assert result_events[0].payload["response"]["content"]
        finally:
            config.data = original


class TestLLMWorkerTurnCancellation:
    async def test_cancelled_turn_skips_llm_execution(self, private_bus, public_bus, state_store):
        factory = LLMFactory()
        provider = _SuccessProvider("should not run")
        factory._providers["mock"] = provider
        runtime = _SimpleLLMRuntime(factory, state_store)
        worker = LLMSessionWorker("s1", private_bus, runtime)
        state_store.mark_turn_cancelled("s1", "t1")

        collected, done, task = await _collect_from_bus(public_bus, 1)
        event = _make_llm_event("mock", "mock-agent-v1", [{"role": "user", "content": "hello"}])

        try:
            await worker._handle(event)
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(done.wait(), timeout=0.1)
        finally:
            task.cancel()

        assert collected == []
        assert provider.calls == []

    async def test_cancel_request_stops_inflight_stream_and_suppresses_completion(
        self, private_bus, public_bus, state_store
    ):
        factory = LLMFactory()
        provider = _SlowStreamingProvider()
        runtime = _SimpleLLMRuntime(factory, state_store)
        factory._providers["mock"] = provider
        worker = LLMSessionWorker("s1", private_bus, runtime)

        collected: list[EventEnvelope] = []
        first_delta = asyncio.Event()

        async def collector():
            async for evt in public_bus.subscribe():
                collected.append(evt)
                if evt.type == LLM_CALL_DELTA:
                    first_delta.set()

        collect_task = asyncio.create_task(collector())
        await asyncio.sleep(0.01)

        request = EventEnvelope(
            type=LLM_CALL_REQUESTED,
            session_id="s1",
            turn_id="t1",
            payload={
                "llm_call_id": "llm_stream_cancel",
                "provider": "mock",
                "model": "mock-agent-v1",
                "messages": [{"role": "user", "content": "repeat abc"}],
                "stream": True,
            },
        )
        cancel = EventEnvelope(
            type=USER_TURN_CANCEL_REQUESTED,
            session_id="s1",
            turn_id="t1",
            payload={"reason": "user_cancel"},
        )

        try:
            await worker._handle(request)
            await asyncio.wait_for(first_delta.wait(), timeout=1)
            await worker._handle(cancel)
            await asyncio.sleep(0.2)
        finally:
            collect_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await collect_task
            await worker.stop()

        delta_events = [event for event in collected if event.type == LLM_CALL_DELTA]
        event_types = [event.type for event in collected]

        assert provider.calls != []
        assert LLM_CALL_STARTED in event_types
        assert len(delta_events) == 1
        assert LLM_CALL_RESULT not in event_types
        assert LLM_CALL_COMPLETED not in event_types
