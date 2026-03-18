import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from agentos.kernel.runtime.workers.tool_worker import ToolSessionWorker
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import USER_QUESTION_ANSWERED


@pytest.fixture
def mock_runtime():
    runtime = MagicMock()
    runtime.registry = MagicMock()
    runtime.path_policy = None
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
    """ask_user handler 应创建 Future 并发布事件"""
    handler = worker._make_ask_user_handler()
    task = asyncio.create_task(handler(
        question="测试？", options=["A", "B"], multi_select=False,
        session_id="test_session", turn_id="turn1", tool_call_id="call1",
    ))
    await asyncio.sleep(0.1)

    assert len(worker._pending_questions) == 1
    assert mock_bus.publish.called

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_ask_user_handler_timeout(worker):
    """超时应返回错误"""
    import agentos.platform.config.config as config_module
    original_get = config_module.config.get
    config_module.config.get = lambda key, default=None: 0.1 if "timeout" in key else original_get(key, default)

    handler = worker._make_ask_user_handler()
    result = await handler(
        question="测试？", options=None, multi_select=False,
        session_id="test_session", turn_id="turn1", tool_call_id="call1",
    )

    assert result["success"] is False
    assert "未在" in result["error"]
    assert len(worker._pending_questions) == 0

    config_module.config.get = original_get


@pytest.mark.asyncio
async def test_ask_user_handler_concurrent_reject(worker):
    """同时只允许一个挂起问题"""
    worker._pending_questions["existing"] = asyncio.Future()

    handler = worker._make_ask_user_handler()
    result = await handler(
        question="测试？", options=None, multi_select=False,
        session_id="test_session", turn_id="turn1", tool_call_id="call1",
    )

    assert result["success"] is False
    assert "已有待回答问题" in result["error"]


@pytest.mark.asyncio
async def test_resolve_question_success(worker):
    """回答成功应设置 Future 结果"""
    question_id = "q1"
    future = asyncio.Future()
    worker._pending_questions[question_id] = future

    event = EventEnvelope(
        type=USER_QUESTION_ANSWERED,
        session_id="test_session", source="test",
        payload={"question_id": question_id, "answer": "A", "cancelled": False},
    )
    worker._resolve_question(event)

    assert future.done()
    result = future.result()
    assert result["success"] is True
    assert result["answer"] == "A"


@pytest.mark.asyncio
async def test_resolve_question_cancelled(worker):
    """取消回答应设置 cancelled 结果"""
    question_id = "q1"
    future = asyncio.Future()
    worker._pending_questions[question_id] = future

    event = EventEnvelope(
        type=USER_QUESTION_ANSWERED,
        session_id="test_session", source="test",
        payload={"question_id": question_id, "cancelled": True},
    )
    worker._resolve_question(event)

    assert future.done()
    result = future.result()
    assert result["success"] is False
    assert "取消" in result["error"]


@pytest.mark.asyncio
async def test_stop_cleans_pending_questions(worker):
    """stop 应取消所有挂起的 Future"""
    future1 = asyncio.Future()
    future2 = asyncio.Future()
    worker._pending_questions["q1"] = future1
    worker._pending_questions["q2"] = future2

    await worker.stop()

    assert future1.cancelled()
    assert future2.cancelled()
    assert len(worker._pending_questions) == 0
