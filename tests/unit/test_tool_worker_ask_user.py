from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import sensenova_claw.kernel.runtime.workers.tool_worker as tool_worker_module
from sensenova_claw.adapters.storage.repository import Repository
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import (
    ERROR_RAISED,
    TOOL_CALL_RESULT,
    USER_QUESTION_ANSWERED,
    USER_QUESTION_ASKED,
)
from sensenova_claw.kernel.runtime.workers.tool_worker import ToolSessionWorker


class _QuickTool:
    async def execute(self, **kwargs):
        _ = kwargs
        return {"ok": True}


class _TimeoutTool:
    async def execute(self, **kwargs):
        _ = kwargs
        raise asyncio.TimeoutError()


class _CaptureSourceAgentTool:
    def __init__(self):
        self.source_agent_id = None

    async def execute(self, **kwargs):
        self.source_agent_id = kwargs.get("_source_agent_id")
        return {"ok": True}


class _ExecutedFlagTool:
    def __init__(self):
        self.executed = False

    async def execute(self, **kwargs):
        _ = kwargs
        self.executed = True
        return {"ok": True}


@pytest.fixture
def mock_runtime():
    runtime = MagicMock()
    runtime.registry = MagicMock()
    runtime.agent_registry = None
    return runtime


@pytest.fixture
def mock_bus():
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def worker(mock_bus, mock_runtime):
    return ToolSessionWorker("test_session", mock_bus, mock_runtime)


@pytest.mark.asyncio
async def test_ask_user_handler_creates_future(worker, mock_bus):
    """ask_user handler 应创建 Future 并发布事件。"""
    handler = worker._make_ask_user_handler()
    task = asyncio.create_task(
        handler(
            question="测试？",
            options=["A", "B"],
            multi_select=False,
            session_id="test_session",
            turn_id="turn1",
            tool_call_id="call1",
        )
    )
    await asyncio.sleep(0.05)

    assert len(worker._pending_questions) == 1
    assert mock_bus.publish.called

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_truncate_result_saves_under_agent_session_dir(tmp_path, mock_bus, monkeypatch):
    """超长工具结果应写到 agents/<agent>/sessions/<session_id>/ 下。"""
    runtime = MagicMock()
    runtime.registry = MagicMock()
    runtime.agent_registry = None
    runtime.repo = Repository(db_path=str(tmp_path / "test.db"))
    await runtime.repo.init()
    monkeypatch.setenv("SENSENOVA_CLAW_HOME", str(tmp_path))

    worker = ToolSessionWorker("agent2agent_abc123", mock_bus, runtime)

    original_get = tool_worker_module.config.get
    tool_worker_module.config.get = lambda key, default=None: {
        "tools.result_truncation.max_tokens": 1,
        "tools.result_truncation.save_dir": "workspace",
    }.get(key, original_get(key, default))
    try:
        result = worker._truncate_result(
            "x" * 100,
            "call_fun_123456",
            agent_id="doc-organizer",
        )
    finally:
        tool_worker_module.config.get = original_get

    expected_dir = (
        tmp_path
        / "agents"
        / "doc-organizer"
        / "sessions"
        / "agent2agent_abc123"
    )
    saved_files = list(expected_dir.glob("tool_result_call_fun_*.txt"))

    assert saved_files
    assert saved_files[0].read_text(encoding="utf-8") == "x" * 100
    assert str(saved_files[0]) in result


@pytest.mark.asyncio
async def test_ask_user_handler_publishes_source_agent_id(worker, mock_bus):
    """ask_user 事件应携带来源 agent_id。"""
    handler = worker._make_ask_user_handler()
    task = asyncio.create_task(
        handler(
            question="测试来源 agent",
            options=["A", "B"],
            multi_select=False,
            session_id="test_session",
            turn_id="turn1",
            tool_call_id="call_source_agent",
            source_agent_id="research",
        )
    )
    await asyncio.sleep(0.05)

    published = [call.args[0] for call in mock_bus.publish.await_args_list]
    asked = next(e for e in published if e.type == USER_QUESTION_ASKED)
    assert asked.payload["source_agent_id"] == "research"

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_ask_user_handler_timeout(worker):
    """超时应返回错误并清理挂起状态。"""
    original_get = tool_worker_module.config.get
    tool_worker_module.config.get = (
        lambda key, default=None: 0.1 if key == "tools.ask_user.timeout" else original_get(key, default)
    )

    try:
        handler = worker._make_ask_user_handler()
        result = await handler(
            question="测试？",
            options=None,
            multi_select=False,
            session_id="test_session",
            turn_id="turn1",
            tool_call_id="call1",
        )
    finally:
        tool_worker_module.config.get = original_get

    assert result["success"] is False
    assert "未在" in result["error"]
    assert len(worker._pending_questions) == 0


@pytest.mark.asyncio
async def test_ask_user_handler_concurrent_reject(worker):
    """同时只允许一个挂起问题。"""
    worker._pending_questions["existing"] = asyncio.Future()

    handler = worker._make_ask_user_handler()
    result = await handler(
        question="测试？",
        options=None,
        multi_select=False,
        session_id="test_session",
        turn_id="turn1",
        tool_call_id="call1",
    )

    assert result["success"] is False
    assert "已有待回答问题" in result["error"]


@pytest.mark.asyncio
async def test_resolve_question_success(worker):
    """回答成功应设置 Future 结果。"""
    question_id = "q1"
    future = asyncio.Future()
    worker._pending_questions[question_id] = future

    event = EventEnvelope(
        type=USER_QUESTION_ANSWERED,
        session_id="test_session",
        source="test",
        payload={"question_id": question_id, "answer": "A", "cancelled": False},
    )
    worker._resolve_question(event)

    assert future.done()
    result = future.result()
    assert result["success"] is True
    assert result["answer"] == "A"


@pytest.mark.asyncio
async def test_resolve_question_cancelled(worker):
    """取消回答应设置 cancelled 结果。"""
    question_id = "q1"
    future = asyncio.Future()
    worker._pending_questions[question_id] = future

    event = EventEnvelope(
        type=USER_QUESTION_ANSWERED,
        session_id="test_session",
        source="test",
        payload={"question_id": question_id, "cancelled": True},
    )
    worker._resolve_question(event)

    assert future.done()
    result = future.result()
    assert result["success"] is False
    assert "取消" in result["error"]


@pytest.mark.asyncio
async def test_stop_cleans_pending_questions(worker):
    """stop 应取消所有挂起的 Future。"""
    future1 = asyncio.Future()
    future2 = asyncio.Future()
    worker._pending_questions["q1"] = future1
    worker._pending_questions["q2"] = future2

    await worker.stop()

    assert future1.cancelled()
    assert future2.cancelled()
    assert len(worker._pending_questions) == 0


@pytest.mark.asyncio
async def test_tool_requested_ask_user_uses_300s_default_timeout(worker, mock_runtime):
    """tools.ask_user.timeout 缺失时，ask_user 默认超时应为 300 秒。"""
    mock_runtime.registry.get.return_value = _QuickTool()

    event = EventEnvelope(
        type="tool.call_requested",
        session_id="test_session",
        turn_id="turn1",
        source="test",
        payload={
            "tool_call_id": "call_ask_user",
            "tool_name": "ask_user",
            "arguments": {"question": "Q"},
        },
    )

    captured_timeout: list[float] = []
    original_wait_for = tool_worker_module.asyncio.wait_for
    original_get = tool_worker_module.config.get

    async def fake_wait_for(awaitable, timeout):
        captured_timeout.append(float(timeout))
        return await awaitable

    def fake_get(key, default=None):
        if key == "tools.ask_user.timeout":
            return default
        return original_get(key, default)

    tool_worker_module.asyncio.wait_for = fake_wait_for
    tool_worker_module.config.get = fake_get
    try:
        await worker._handle_tool_requested(event)
    finally:
        tool_worker_module.asyncio.wait_for = original_wait_for
        tool_worker_module.config.get = original_get

    assert captured_timeout
    assert captured_timeout[0] == 300


@pytest.mark.asyncio
async def test_tool_requested_timeout_error_message_not_empty(worker, mock_runtime, mock_bus):
    """TimeoutError 无文案时，应回落为异常类型名，避免前端显示 Unknown Error。"""
    mock_runtime.registry.get.return_value = _TimeoutTool()

    event = EventEnvelope(
        type="tool.call_requested",
        session_id="test_session",
        turn_id="turn1",
        source="test",
        payload={
            "tool_call_id": "call_timeout",
            "tool_name": "ask_user",
            "arguments": {"question": "Q"},
        },
    )

    await worker._handle_tool_requested(event)

    published = [call.args[0] for call in mock_bus.publish.await_args_list]
    error_event = next(e for e in published if e.type == ERROR_RAISED)
    result_event = next(e for e in published if e.type == TOOL_CALL_RESULT)

    assert error_event.payload["error_message"] == "TimeoutError"
    assert "TimeoutError" in str(result_event.payload["error"])


@pytest.mark.asyncio
async def test_tool_requested_injects_source_agent_id(worker, mock_runtime):
    """tool.execute 应接收到 _source_agent_id。"""
    tool = _CaptureSourceAgentTool()
    mock_runtime.registry.get.return_value = tool

    event = EventEnvelope(
        type="tool.call_requested",
        session_id="test_session",
        turn_id="turn1",
        source="test",
        payload={
            "tool_call_id": "call_source",
            "tool_name": "read_file",
            "arguments": {"path": "README.md"},
            "_source_agent_id": "research",
        },
    )

    await worker._handle_tool_requested(event)

    assert tool.source_agent_id == "research"


@pytest.mark.asyncio
async def test_tool_requested_rejects_disabled_tool_for_agent(worker, mock_runtime, mock_bus, tmp_path, monkeypatch):
    """当工具被当前 agent 禁用时，不应真正执行工具。"""
    tool = _ExecutedFlagTool()
    mock_runtime.registry.get.return_value = tool
    mock_runtime.sensenova_claw_home = str(tmp_path)
    monkeypatch.setenv("SENSENOVA_CLAW_HOME", str(tmp_path))
    (tmp_path / ".agent_preferences.json").write_text(
        '{"agent_tools": {"research": {"read_file": false}}}',
        encoding="utf-8",
    )

    event = EventEnvelope(
        type="tool.call_requested",
        session_id="test_session",
        turn_id="turn1",
        source="test",
        payload={
            "tool_call_id": "call_disabled",
            "tool_name": "read_file",
            "arguments": {"path": "README.md"},
            "_source_agent_id": "research",
        },
    )

    await worker._handle_tool_requested(event)

    published = [call.args[0] for call in mock_bus.publish.await_args_list]
    result_event = next(e for e in published if e.type == TOOL_CALL_RESULT)

    assert tool.executed is False
    assert result_event.payload["success"] is False
    assert "工具已被当前 Agent 禁用" in str(result_event.payload["result"])
