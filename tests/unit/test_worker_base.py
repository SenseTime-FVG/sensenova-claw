"""SessionWorker 基类单元测试 — 使用真实组件，无 mock"""
from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from agentos.kernel.events.bus import PublicEventBus, PrivateEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.runtime.workers.base import SessionWorker


class DummyWorker(SessionWorker):
    """用于测试的具体实现"""

    def __init__(self, session_id: str, bus: PrivateEventBus):
        super().__init__(session_id, bus)
        self.handled_events: list[EventEnvelope] = []
        self.raise_on_handle = False

    async def _handle(self, event: EventEnvelope) -> None:
        if self.raise_on_handle:
            raise ValueError("模拟处理异常")
        self.handled_events.append(event)


@pytest.fixture
def public_bus():
    return PublicEventBus()


@pytest.fixture
def private_bus(public_bus):
    return PrivateEventBus("s1", public_bus)


class TestSessionWorkerInit:
    """初始化测试"""

    def test_init_stores_session_and_bus(self, private_bus):
        worker = DummyWorker("s1", private_bus)
        assert worker.session_id == "s1"
        assert worker.bus is private_bus
        assert worker._task is None


class TestSessionWorkerStartStop:
    """启动/停止生命周期测试"""

    async def test_start_creates_task(self, private_bus):
        worker = DummyWorker("s1", private_bus)
        await worker.start()
        assert worker._task is not None
        assert not worker._task.done()
        await worker.stop()

    async def test_stop_cancels_task(self, private_bus):
        worker = DummyWorker("s1", private_bus)
        await worker.start()
        assert worker._task is not None
        await worker.stop()
        assert worker._task.done()

    async def test_stop_noop_when_no_task(self, private_bus):
        """没有 start 就 stop 不会报错"""
        worker = DummyWorker("s1", private_bus)
        await worker.stop()


class TestSessionWorkerLoop:
    """事件循环测试"""

    async def test_loop_dispatches_events(self, private_bus):
        """事件循环正确分发事件到 _handle"""
        worker = DummyWorker("s1", private_bus)
        await worker.start()
        # 等待 worker 的 _loop 完成订阅
        await asyncio.sleep(0.02)

        e1 = EventEnvelope(type="test.event", session_id="s1", payload={"k": "v1"})
        e2 = EventEnvelope(type="test.event2", session_id="s1", payload={"k": "v2"})
        await private_bus.deliver(e1)
        await private_bus.deliver(e2)

        await asyncio.sleep(0.05)
        await worker.stop()
        assert len(worker.handled_events) == 2
        assert worker.handled_events[0].payload["k"] == "v1"

    async def test_loop_continues_after_handle_error(self, private_bus):
        """_handle 抛异常后循环继续处理下一个事件"""
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

        worker = ErrorOnFirstWorker("s1", private_bus)
        await worker.start()
        await asyncio.sleep(0.02)

        await private_bus.deliver(EventEnvelope(type="t1", session_id="s1"))
        await private_bus.deliver(EventEnvelope(type="t2", session_id="s1"))

        await asyncio.sleep(0.05)
        await worker.stop()
        assert len(worker.handled) == 1
        assert worker.handled[0].type == "t2"


class TestSessionWorkerHandleNotImplemented:
    """基类 _handle 抛 NotImplementedError"""

    async def test_base_handle_raises(self, private_bus):
        worker = SessionWorker("s1", private_bus)
        with pytest.raises(NotImplementedError):
            await worker._handle(EventEnvelope(type="x", session_id="s1"))
