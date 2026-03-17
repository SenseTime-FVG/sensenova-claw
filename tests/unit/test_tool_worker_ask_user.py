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
async def test_handle_ask_user_creates_future(worker, mock_bus):
    params = {"question": "测试？", "options": ["A", "B"], "multi_select": False}
    event = EventEnvelope(
        type="tool.call_requested",
        session_id="test_session",
        turn_id="turn1",
        source="test",
        payload={}
    )

    task = asyncio.create_task(worker._handle_ask_user(params, "call1", event))
    await asyncio.sleep(0.1)

    assert len(worker._pending_questions) == 1
    assert mock_bus.publish.called

    # 取消任务清理
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_handle_ask_user_timeout(worker):
    params = {"question": "测试？"}
    event = EventEnvelope(
        type="tool.call_requested",
        session_id="test_session",
        turn_id="turn1",
        source="test",
        payload={}
    )

    # 设置极短超时
    import agentos.platform.config.config as config_module
    original_get = config_module.config.get
    config_module.config.get = lambda key, default=None: 0.1 if "timeout" in key else original_get(key, default)

    result = await worker._handle_ask_user(params, "call1", event)

    assert result["success"] is False
    assert "未在" in result["error"]
    assert len(worker._pending_questions) == 0

    config_module.config.get = original_get


@pytest.mark.asyncio
async def test_handle_ask_user_concurrent_reject(worker):
    params = {"question": "测试？"}
    event = EventEnvelope(
        type="tool.call_requested",
        session_id="test_session",
        turn_id="turn1",
        source="test",
        payload={}
    )

    # 模拟已有待处理问题
    worker._pending_questions["existing"] = asyncio.Future()

    result = await worker._handle_ask_user(params, "call1", event)

    assert result["success"] is False
    assert "已有待回答问题" in result["error"]


@pytest.mark.asyncio
async def test_handle_question_answered_success(worker):
    question_id = "q1"
    future = asyncio.Future()
    worker._pending_questions[question_id] = future

    event = EventEnvelope(
        type=USER_QUESTION_ANSWERED,
        session_id="test_session",
        source="test",
        payload={"question_id": question_id, "answer": "A", "cancelled": False}
    )

    await worker._handle_question_answered(event)

    assert future.done()
    result = future.result()
    assert result["success"] is True
    assert result["answer"] == "A"


@pytest.mark.asyncio
async def test_handle_question_answered_cancelled(worker):
    question_id = "q1"
    future = asyncio.Future()
    worker._pending_questions[question_id] = future

    event = EventEnvelope(
        type=USER_QUESTION_ANSWERED,
        session_id="test_session",
        source="test",
        payload={"question_id": question_id, "cancelled": True}
    )

    await worker._handle_question_answered(event)

    assert future.done()
    result = future.result()
    assert result["success"] is False
    assert "取消" in result["error"]


@pytest.mark.asyncio
async def test_stop_cleans_pending_questions(worker):
    future1 = asyncio.Future()
    future2 = asyncio.Future()
    worker._pending_questions["q1"] = future1
    worker._pending_questions["q2"] = future2

    await worker.stop()

    assert future1.cancelled()
    assert future2.cancelled()
    assert len(worker._pending_questions) == 0
