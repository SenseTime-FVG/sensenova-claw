"""WebSocketForwarder 和 ConnectionManager 单元测试 — 使用 asyncio 队列模拟 WebSocket，无 mock"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import (
    AGENT_STEP_COMPLETED,
    AGENT_STEP_STARTED,
    ERROR_RAISED,
    LLM_CALL_COMPLETED,
    LLM_CALL_REQUESTED,
    LLM_CALL_RESULT,
    TOOL_CALL_REQUESTED,
    TOOL_CALL_RESULT,
)
from agentos.kernel.runtime.publisher import EventPublisher
from agentos.kernel.runtime.ws_forwarder import (
    AGENT_UPDATE_TITLE_COMPLETED,
    ConnectionManager,
    WebSocketForwarder,
)


# ── 轻量 WebSocket 替身（纯 asyncio，无 mock）─────────────


class FakeWebSocket:
    """用 asyncio.Queue 模拟 WebSocket 连接"""

    def __init__(self):
        self.accepted = False
        self.sent_messages: list[dict] = []
        self._should_fail = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data: dict[str, Any]) -> None:
        if self._should_fail:
            raise ConnectionError("断开")
        self.sent_messages.append(data)

    def set_fail(self) -> None:
        """下次 send_json 时抛异常"""
        self._should_fail = True


# ── ConnectionManager 测试 ────────────────────────────────


class TestConnectionManager:
    """ConnectionManager 连接管理测试"""

    async def test_connect_accepts_and_adds(self):
        mgr = ConnectionManager()
        ws = FakeWebSocket()
        await mgr.connect(ws)
        assert ws in mgr.connections
        assert ws.accepted

    def test_disconnect_removes_connection(self):
        mgr = ConnectionManager()
        ws = FakeWebSocket()
        mgr.connections.add(ws)
        mgr.session_bindings["s1"] = {ws}
        mgr.disconnect(ws)
        assert ws not in mgr.connections
        assert ws not in mgr.session_bindings["s1"]

    def test_disconnect_nonexistent_noop(self):
        mgr = ConnectionManager()
        ws = FakeWebSocket()
        mgr.disconnect(ws)  # 不抛异常

    def test_bind_session(self):
        mgr = ConnectionManager()
        ws = FakeWebSocket()
        mgr.bind_session("s1", ws)
        assert ws in mgr.session_bindings["s1"]

    def test_bind_session_multiple(self):
        """同一 session 绑定多个 ws"""
        mgr = ConnectionManager()
        ws1, ws2 = FakeWebSocket(), FakeWebSocket()
        mgr.bind_session("s1", ws1)
        mgr.bind_session("s1", ws2)
        assert len(mgr.session_bindings["s1"]) == 2

    async def test_send_json(self):
        mgr = ConnectionManager()
        ws = FakeWebSocket()
        await mgr.send_json(ws, {"type": "test"})
        assert ws.sent_messages == [{"type": "test"}]

    async def test_send_to_session(self):
        mgr = ConnectionManager()
        ws1, ws2 = FakeWebSocket(), FakeWebSocket()
        mgr.session_bindings["s1"] = {ws1, ws2}
        await mgr.send_to_session("s1", {"type": "x"})
        assert len(ws1.sent_messages) == 1
        assert len(ws2.sent_messages) == 1

    async def test_send_to_session_disconnects_on_error(self):
        """发送失败时自动断开连接"""
        mgr = ConnectionManager()
        ws_ok = FakeWebSocket()
        ws_bad = FakeWebSocket()
        ws_bad.set_fail()
        mgr.connections = {ws_ok, ws_bad}
        mgr.session_bindings["s1"] = {ws_ok, ws_bad}
        await mgr.send_to_session("s1", {"type": "x"})
        assert ws_bad not in mgr.connections

    async def test_send_to_session_no_bindings(self):
        """没有绑定的 session 不抛异常"""
        mgr = ConnectionManager()
        await mgr.send_to_session("nonexistent", {"type": "x"})


# ── WebSocketForwarder._map 测试 ──────────────────────────


class TestForwarderMap:
    """事件映射测试"""

    def _make_forwarder(self):
        bus = PublicEventBus()
        publisher = EventPublisher(bus)
        mgr = ConnectionManager()
        return WebSocketForwarder(publisher, mgr)

    def test_map_agent_step_started(self):
        fwd = self._make_forwarder()
        event = EventEnvelope(
            type=AGENT_STEP_STARTED, session_id="s1",
            payload={"step_type": "llm_call"},
        )
        result = fwd._map(event)
        assert result["type"] == "agent_thinking"
        assert result["session_id"] == "s1"

    def test_map_llm_call_requested(self):
        fwd = self._make_forwarder()
        event = EventEnvelope(type=LLM_CALL_REQUESTED, session_id="s1")
        result = fwd._map(event)
        assert result["type"] == "agent_thinking"
        assert result["payload"]["step_type"] == "llm_call"

    def test_map_llm_call_result(self):
        fwd = self._make_forwarder()
        event = EventEnvelope(
            type=LLM_CALL_RESULT, session_id="s1",
            payload={
                "llm_call_id": "llm_1",
                "response": {"content": "hello", "tool_calls": []},
                "usage": {"total_tokens": 10},
                "finish_reason": "stop",
            },
        )
        result = fwd._map(event)
        assert result["type"] == "llm_result"
        assert result["payload"]["content"] == "hello"
        assert result["payload"]["finish_reason"] == "stop"

    def test_map_llm_call_completed_returns_none(self):
        """LLM_CALL_COMPLETED 不转发"""
        fwd = self._make_forwarder()
        event = EventEnvelope(type=LLM_CALL_COMPLETED, session_id="s1")
        assert fwd._map(event) is None

    def test_map_tool_call_requested(self):
        fwd = self._make_forwarder()
        event = EventEnvelope(
            type=TOOL_CALL_REQUESTED, session_id="s1",
            payload={"tool_call_id": "tc1", "tool_name": "bash_command", "arguments": {"cmd": "ls"}},
        )
        result = fwd._map(event)
        assert result["type"] == "tool_execution"
        assert result["payload"]["status"] == "running"

    def test_map_tool_call_result(self):
        fwd = self._make_forwarder()
        event = EventEnvelope(
            type=TOOL_CALL_RESULT, session_id="s1",
            payload={"tool_call_id": "tc1", "tool_name": "bash_command", "result": "output", "success": True},
        )
        result = fwd._map(event)
        assert result["type"] == "tool_result"
        assert result["payload"]["result"] == "output"
        assert result["payload"]["success"] is True

    def test_map_agent_step_completed(self):
        fwd = self._make_forwarder()
        event = EventEnvelope(
            type=AGENT_STEP_COMPLETED, session_id="s1", turn_id="t1",
            payload={"result": {"content": "完成"}},
        )
        result = fwd._map(event)
        assert result["type"] == "turn_completed"
        assert result["payload"]["final_response"] == "完成"

    def test_map_error_raised(self):
        fwd = self._make_forwarder()
        event = EventEnvelope(
            type=ERROR_RAISED, session_id="s1",
            payload={"error_type": "RuntimeError", "error_message": "boom", "context": {}},
        )
        result = fwd._map(event)
        assert result["type"] == "error"
        assert result["payload"]["message"] == "boom"

    def test_map_title_updated(self):
        fwd = self._make_forwarder()
        event = EventEnvelope(
            type=AGENT_UPDATE_TITLE_COMPLETED, session_id="s1",
            payload={"title": "新标题", "success": True},
        )
        result = fwd._map(event)
        assert result["type"] == "title_updated"
        assert result["payload"]["title"] == "新标题"

    def test_map_unknown_returns_none(self):
        fwd = self._make_forwarder()
        event = EventEnvelope(type="random.event", session_id="s1")
        assert fwd._map(event) is None


# ── WebSocketForwarder 启动/停止测试 ──────────────────────


class TestForwarderStartStop:
    """启动/停止测试"""

    async def test_start_creates_task(self):
        bus = PublicEventBus()
        publisher = EventPublisher(bus)
        mgr = ConnectionManager()
        fwd = WebSocketForwarder(publisher, mgr)
        await fwd.start()
        assert fwd._task is not None
        await fwd.stop()

    async def test_stop_without_start(self):
        bus = PublicEventBus()
        publisher = EventPublisher(bus)
        mgr = ConnectionManager()
        fwd = WebSocketForwarder(publisher, mgr)
        await fwd.stop()  # 不抛异常
