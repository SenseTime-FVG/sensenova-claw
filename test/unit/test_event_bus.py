"""B02/B03: PublicEventBus 发布/订阅 + PrivateEventBus 会话隔离"""
import asyncio
import pytest
from app.events.bus import PublicEventBus, PrivateEventBus
from app.events.envelope import EventEnvelope

pytestmark = pytest.mark.asyncio


class TestPublicEventBus:
    async def test_publish_subscribe(self):
        bus = PublicEventBus()
        received = []

        async def _sub():
            async for ev in bus.subscribe():
                received.append(ev)
                if len(received) >= 2:
                    return

        task = asyncio.create_task(_sub())
        await asyncio.sleep(0)

        await bus.publish(EventEnvelope(type="a", session_id="s1"))
        await bus.publish(EventEnvelope(type="b", session_id="s2"))
        await asyncio.wait_for(task, timeout=2)

        assert len(received) == 2
        assert received[0].type == "a"
        assert received[1].type == "b"

    async def test_multiple_subscribers(self):
        bus = PublicEventBus()
        r1, r2 = [], []

        async def _s1():
            async for ev in bus.subscribe():
                r1.append(ev); return

        async def _s2():
            async for ev in bus.subscribe():
                r2.append(ev); return

        t1 = asyncio.create_task(_s1())
        t2 = asyncio.create_task(_s2())
        await asyncio.sleep(0)
        await bus.publish(EventEnvelope(type="x", session_id="s"))
        await asyncio.wait_for(asyncio.gather(t1, t2), timeout=2)
        assert len(r1) == 1 and len(r2) == 1


class TestPrivateEventBus:
    async def test_session_isolation(self):
        pub = PublicEventBus()
        priv = PrivateEventBus(session_id="s1", public_bus=pub)
        received_private = []

        async def _sub():
            async for ev in priv.subscribe():
                received_private.append(ev)
                if len(received_private) >= 1:
                    return

        task = asyncio.create_task(_sub())
        await asyncio.sleep(0)
        await priv.publish(EventEnvelope(type="t", session_id="s1"))
        await asyncio.wait_for(task, timeout=2)
        assert len(received_private) == 1

    async def test_deliver_no_backflow(self):
        """deliver 不应回流到 PublicEventBus"""
        pub = PublicEventBus()
        pub_received = []

        async def _pub_sub():
            async for ev in pub.subscribe():
                pub_received.append(ev); return

        pub_task = asyncio.create_task(_pub_sub())
        await asyncio.sleep(0)

        priv = PrivateEventBus(session_id="s1", public_bus=pub)
        priv_received = []

        async def _priv_sub():
            async for ev in priv.subscribe():
                priv_received.append(ev); return

        priv_task = asyncio.create_task(_priv_sub())
        await asyncio.sleep(0)

        await priv.deliver(EventEnvelope(type="d", session_id="s1"))
        await asyncio.wait_for(priv_task, timeout=2)
        assert len(priv_received) == 1

        # pub_task 不应收到 deliver 的事件，给一小段超时
        try:
            await asyncio.wait_for(pub_task, timeout=0.2)
        except asyncio.TimeoutError:
            pass
        # deliver 不会发到 public bus
        assert len(pub_received) == 0
        pub_task.cancel()

    async def test_close(self):
        pub = PublicEventBus()
        priv = PrivateEventBus(session_id="s", public_bus=pub)
        priv.close()
        assert priv._closed is True
