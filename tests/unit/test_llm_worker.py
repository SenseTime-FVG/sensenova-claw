"""LLMSessionWorker 单元测试"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import (
    ERROR_RAISED,
    LLM_CALL_COMPLETED,
    LLM_CALL_REQUESTED,
    LLM_CALL_RESULT,
    LLM_CALL_STARTED,
)
from agentos.kernel.runtime.workers.llm_worker import LLMSessionWorker


def _make_worker():
    """创建一个 LLMSessionWorker，mock 所有外部依赖"""
    bus = AsyncMock()
    bus.publish = AsyncMock()
    runtime = MagicMock()
    provider = AsyncMock()
    runtime.factory.get_provider.return_value = provider
    worker = LLMSessionWorker("s1", bus, runtime)
    return worker, bus, runtime, provider


class TestLLMWorkerHandle:
    """_handle 路由测试"""

    @pytest.mark.asyncio
    async def test_ignores_non_llm_requested_events(self):
        worker, bus, _, _ = _make_worker()
        event = EventEnvelope(type="other.event", session_id="s1")
        await worker._handle(event)
        bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_routes_llm_requested(self):
        worker, bus, _, provider = _make_worker()
        provider.call.return_value = {"content": "hi", "tool_calls": []}
        event = EventEnvelope(
            type=LLM_CALL_REQUESTED,
            session_id="s1",
            turn_id="t1",
            payload={
                "llm_call_id": "llm_1",
                "provider": "openai",
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
        await worker._handle(event)
        # 应该发布 LLM_CALL_STARTED + LLM_CALL_RESULT + LLM_CALL_COMPLETED
        assert bus.publish.call_count == 3


class TestLLMWorkerSuccess:
    """LLM 调用成功路径"""

    @pytest.mark.asyncio
    async def test_publishes_correct_event_sequence(self):
        worker, bus, _, provider = _make_worker()
        provider.call.return_value = {
            "content": "回答内容",
            "tool_calls": [],
            "usage": {"total_tokens": 100},
            "finish_reason": "stop",
        }
        event = EventEnvelope(
            type=LLM_CALL_REQUESTED,
            session_id="s1",
            turn_id="t1",
            payload={
                "llm_call_id": "llm_abc",
                "provider": "openai",
                "model": "gpt-4o",
                "messages": [],
            },
        )
        await worker._handle(event)

        calls = bus.publish.call_args_list
        # 第一个事件: LLM_CALL_STARTED
        assert calls[0][0][0].type == LLM_CALL_STARTED
        assert calls[0][0][0].trace_id == "llm_abc"
        # 第二个事件: LLM_CALL_RESULT
        result_event = calls[1][0][0]
        assert result_event.type == LLM_CALL_RESULT
        assert result_event.payload["response"]["content"] == "回答内容"
        assert result_event.payload["finish_reason"] == "stop"
        # 第三个事件: LLM_CALL_COMPLETED
        assert calls[2][0][0].type == LLM_CALL_COMPLETED

    @pytest.mark.asyncio
    async def test_passes_tool_calls_through(self):
        worker, bus, _, provider = _make_worker()
        tc = [{"id": "tc1", "name": "bash_command", "arguments": {"cmd": "ls"}}]
        provider.call.return_value = {"content": "", "tool_calls": tc}
        event = EventEnvelope(
            type=LLM_CALL_REQUESTED,
            session_id="s1",
            turn_id="t1",
            payload={
                "llm_call_id": "llm_1",
                "provider": "openai",
                "model": "gpt-4o",
                "messages": [],
                "tools": [{"name": "bash_command"}],
            },
        )
        await worker._handle(event)
        result_event = bus.publish.call_args_list[1][0][0]
        assert result_event.payload["response"]["tool_calls"] == tc

    @pytest.mark.asyncio
    async def test_passes_reasoning_details(self):
        """透传 reasoning_details 字段"""
        worker, bus, _, provider = _make_worker()
        provider.call.return_value = {
            "content": "x",
            "tool_calls": [],
            "reasoning_details": [{"type": "thought", "text": "想一想"}],
        }
        event = EventEnvelope(
            type=LLM_CALL_REQUESTED,
            session_id="s1",
            turn_id="t1",
            payload={"llm_call_id": "llm_1", "provider": "openai", "model": "m", "messages": []},
        )
        await worker._handle(event)
        result_event = bus.publish.call_args_list[1][0][0]
        assert "reasoning_details" in result_event.payload["response"]


class TestLLMWorkerError:
    """LLM 调用失败路径"""

    @pytest.mark.asyncio
    async def test_error_publishes_error_and_fallback_result(self):
        worker, bus, _, provider = _make_worker()
        provider.call.side_effect = RuntimeError("API 超时")
        event = EventEnvelope(
            type=LLM_CALL_REQUESTED,
            session_id="s1",
            turn_id="t1",
            payload={"llm_call_id": "llm_1", "provider": "openai", "model": "m", "messages": []},
        )
        await worker._handle(event)

        calls = bus.publish.call_args_list
        # LLM_CALL_STARTED + ERROR_RAISED + LLM_CALL_RESULT(fallback) + LLM_CALL_COMPLETED
        assert len(calls) == 4
        # ERROR_RAISED
        err = calls[1][0][0]
        assert err.type == ERROR_RAISED
        assert "API 超时" in err.payload["error_message"]
        # fallback LLM_CALL_RESULT
        fallback = calls[2][0][0]
        assert fallback.type == LLM_CALL_RESULT
        assert "LLM调用失败" in fallback.payload["response"]["content"]
        assert fallback.payload["finish_reason"] == "error"
        # LLM_CALL_COMPLETED 仍然发布
        assert calls[3][0][0].type == LLM_CALL_COMPLETED


class TestLLMWorkerConfigFallback:
    """配置回退测试"""

    @pytest.mark.asyncio
    @patch("agentos.kernel.runtime.workers.llm_worker.config")
    async def test_uses_config_defaults_when_payload_empty(self, mock_config):
        mock_config.get.side_effect = lambda key, default=None: {
            "agent.default_model": "fallback-model",
            "agent.provider": "mock",
            "agent.default_temperature": 0.5,
        }.get(key, default)

        worker, bus, _, provider = _make_worker()
        provider.call.return_value = {"content": "ok", "tool_calls": []}
        event = EventEnvelope(
            type=LLM_CALL_REQUESTED,
            session_id="s1",
            turn_id="t1",
            payload={"llm_call_id": "llm_1", "messages": []},
        )
        await worker._handle(event)
        # provider.call 应用 fallback model 和 temperature
        call_kwargs = provider.call.call_args
        assert call_kwargs.kwargs.get("model") == "fallback-model" or call_kwargs[1].get("model") == "fallback-model"
