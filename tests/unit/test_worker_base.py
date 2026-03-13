"""SessionWorker 基类单元测试"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.runtime.workers.base import SessionWorker


class DummyWorker(SessionWorker):
    """用于测试的具体实现"""

    def __init__(self, session_id, bus):
        super().__init__(session_id, bus)
        self.handled_events: list[EventEnvelope] = []
        self.raise_on_handle = False

    async def _handle(self, event: EventEnvelope) -> None:
        if self.raise_on_handle:
            raise ValueError("模拟处理异常")
        self.handled_events.append(event)


class TestSessionWorkerInit:
    """初始化测试"""

    def test_init_stores_session_and_bus(self):
        bus = MagicMock()
        worker = DummyWorker("s1", bus)
        assert worker.session_id == "s1"
        assert worker.bus is bus
        assert worker._task is None


class TestSessionWorkerStartStop:
    """启动/停止生命周期测试"""

    @pytest.mark.asyncio
    async def test_start_creates_task(self):
        bus = MagicMock()
        # subscribe 返回空的异步迭代器
        async def empty_iter():
            return
            yield  # noqa: make it async generator

        bus.subscribe = empty_iter
        worker = DummyWorker("s1", bus)
        await worker.start()
        assert worker._task is not None
        assert not worker._task.done()
        # 清理
        await worker.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        bus = MagicMock()
        event_sent = asyncio.Event()

        async def blocking_iter():
            await event_sent.wait()  # 永远不会被 set，模拟阻塞
            return
            yield

        bus.subscribe = blocking_iter
        worker = DummyWorker("s1", bus)
        await worker.start()
        assert worker._task is not None
        await worker.stop()
        assert worker._task.done()

    @pytest.mark.asyncio
    async def test_stop_noop_when_no_task(self):
        """没有 start 就 stop 不会报错"""
        bus = MagicMock()
        worker = DummyWorker("s1", bus)
        await worker.stop()  # 不抛异常


class TestSessionWorkerLoop:
    """事件循环测试"""

    @pytest.mark.asyncio
    async def test_loop_dispatches_events(self):
        """事件循环正确分发事件到 _handle"""
        bus = MagicMock()
        events = [
            EventEnvelope(type="test.event", session_id="s1", payload={"k": "v1"}),
            EventEnvelope(type="test.event2", session_id="s1", payload={"k": "v2"}),
        ]

        async def iter_events():
            for e in events:
                yield e

        bus.subscribe = iter_events
        worker = DummyWorker("s1", bus)
        await worker.start()
        await asyncio.sleep(0.05)
        await worker.stop()
        assert len(worker.handled_events) == 2
        assert worker.handled_events[0].payload["k"] == "v1"

    @pytest.mark.asyncio
    async def test_loop_continues_after_handle_error(self):
        """_handle 抛异常后循环继续处理下一个事件"""
        bus = MagicMock()
        call_count = 0

        class ErrorOnFirstWorker(SessionWorker):
            def __init__(self, sid, b):
                super().__init__(sid, b)
                self.handled = []

            async def _handle(self, event):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise RuntimeError("第一次失败")
                self.handled.append(event)

        events = [
            EventEnvelope(type="t1", session_id="s1"),
            EventEnvelope(type="t2", session_id="s1"),
        ]

        async def iter_events():
            for e in events:
                yield e

        bus.subscribe = iter_events
        worker = ErrorOnFirstWorker("s1", bus)
        await worker.start()
        await asyncio.sleep(0.05)
        await worker.stop()
        # 第二个事件应该被处理
        assert len(worker.handled) == 1
        assert worker.handled[0].type == "t2"


class TestSessionWorkerHandleNotImplemented:
    """基类 _handle 抛 NotImplementedError"""

    @pytest.mark.asyncio
    async def test_base_handle_raises(self):
        bus = MagicMock()
        worker = SessionWorker("s1", bus)
        with pytest.raises(NotImplementedError):
            await worker._handle(EventEnvelope(type="x", session_id="s1"))
