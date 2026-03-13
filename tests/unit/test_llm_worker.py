"""LLMSessionWorker 单元测试 — 使用真实组件，无 mock"""
from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from agentos.adapters.llm.base import LLMProvider
from agentos.adapters.llm.factory import LLMFactory
from agentos.adapters.llm.providers.mock_provider import MockProvider
from agentos.kernel.events.bus import PublicEventBus, PrivateEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import (
    ERROR_RAISED,
    LLM_CALL_COMPLETED,
    LLM_CALL_REQUESTED,
    LLM_CALL_RESULT,
    LLM_CALL_STARTED,
)
from agentos.kernel.runtime.workers.llm_worker import LLMSessionWorker


# ── 辅助组件 ──────────────────────────────────────────────


class _ErrorProvider(LLMProvider):
    """始终抛异常的 LLM Provider，用于测试错误路径"""

    async def call(self, **kwargs):
        raise RuntimeError("API 超时")


class _SimpleLLMRuntime:
    """轻量级 LLMRuntime 替身，持有真实 LLMFactory"""

    def __init__(self, factory: LLMFactory):
        self.factory = factory


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
def runtime(factory):
    return _SimpleLLMRuntime(factory)


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
        # 不抛异常即可

    async def test_routes_llm_requested(self, private_bus, public_bus, runtime):
        worker = LLMSessionWorker("s1", private_bus, runtime)
        collected, done, task = await _collect_from_bus(public_bus, 3)

        event = EventEnvelope(
            type=LLM_CALL_REQUESTED,
            session_id="s1",
            turn_id="t1",
            payload={
                "llm_call_id": "llm_1",
                "provider": "mock",
                "model": "mock-agent-v1",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
        await worker._handle(event)
        await asyncio.wait_for(done.wait(), timeout=5)
        task.cancel()

        types = [e.type for e in collected]
        assert LLM_CALL_STARTED in types
        assert LLM_CALL_RESULT in types
        assert LLM_CALL_COMPLETED in types


# ── LLM 调用成功路径 ─────────────────────────────────────


class TestLLMWorkerSuccess:
    """LLM 调用成功路径"""

    async def test_publishes_correct_event_sequence(self, private_bus, public_bus, runtime):
        worker = LLMSessionWorker("s1", private_bus, runtime)
        collected, done, task = await _collect_from_bus(public_bus, 3)

        event = EventEnvelope(
            type=LLM_CALL_REQUESTED,
            session_id="s1",
            turn_id="t1",
            payload={
                "llm_call_id": "llm_abc",
                "provider": "mock",
                "model": "mock-agent-v1",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
        await worker._handle(event)
        await asyncio.wait_for(done.wait(), timeout=5)
        task.cancel()

        assert collected[0].type == LLM_CALL_STARTED
        assert collected[0].trace_id == "llm_abc"
        result_event = collected[1]
        assert result_event.type == LLM_CALL_RESULT
        assert result_event.payload["response"]["content"]
        assert result_event.payload["finish_reason"] == "stop"
        assert collected[2].type == LLM_CALL_COMPLETED

    async def test_passes_tool_calls_through(self, private_bus, public_bus, runtime):
        """请求包含英超冠亚军关键词时，mock provider 返回 tool_calls"""
        worker = LLMSessionWorker("s1", private_bus, runtime)
        collected, done, task = await _collect_from_bus(public_bus, 3)

        event = EventEnvelope(
            type=LLM_CALL_REQUESTED,
            session_id="s1",
            turn_id="t1",
            payload={
                "llm_call_id": "llm_1",
                "provider": "mock",
                "model": "mock-agent-v1",
                "messages": [{"role": "user", "content": "英超冠亚军是谁"}],
                "tools": [{"name": "serper_search"}],
            },
        )
        await worker._handle(event)
        await asyncio.wait_for(done.wait(), timeout=5)
        task.cancel()

        result_event = [e for e in collected if e.type == LLM_CALL_RESULT][0]
        tc = result_event.payload["response"]["tool_calls"]
        assert len(tc) > 0
        assert tc[0]["name"] == "serper_search"


# ── LLM 调用失败路径 ─────────────────────────────────────


class TestLLMWorkerError:
    """LLM 调用失败路径"""

    async def test_error_publishes_error_and_fallback_result(self, private_bus, public_bus):
        factory = LLMFactory()
        factory._providers["error"] = _ErrorProvider()
        runtime = _SimpleLLMRuntime(factory)
        worker = LLMSessionWorker("s1", private_bus, runtime)

        collected, done, task = await _collect_from_bus(public_bus, 4)

        event = EventEnvelope(
            type=LLM_CALL_REQUESTED,
            session_id="s1",
            turn_id="t1",
            payload={
                "llm_call_id": "llm_1",
                "provider": "error",
                "model": "m",
                "messages": [{"role": "user", "content": "test"}],
            },
        )
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


# ── 配置回退测试 ──────────────────────────────────────────


class TestLLMWorkerConfigFallback:
    """不传 provider/model 时使用全局配置默认值"""

    async def test_uses_config_defaults_when_payload_empty(self, private_bus, public_bus, runtime):
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
