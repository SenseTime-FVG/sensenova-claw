"""B04: BusRouter Public↔Private 路由"""
import asyncio
import pytest
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.router import BusRouter
from sensenova_claw.kernel.events.types import USER_INPUT

pytestmark = pytest.mark.asyncio


class TestBusRouter:
    async def test_create_private_bus_on_user_input(self):
        bus = PublicEventBus()
        router = BusRouter(public_bus=bus, ttl_seconds=60, gc_interval=60)
        await router.start()
        # 等待路由循环订阅完毕
        await asyncio.sleep(0.05)

        # 发布 USER_INPUT 事件，应自动创建私有总线
        await bus.publish(EventEnvelope(
            type=USER_INPUT, session_id="s1",
            source="test", payload={"content": "hi"},
        ))
        # 等待路由循环处理事件
        for _ in range(10):
            await asyncio.sleep(0.05)
            if router.get("s1") is not None:
                break

        priv = router.get("s1")
        assert priv is not None
        assert priv.session_id == "s1"

        await router.stop()

    async def test_get_or_create(self):
        bus = PublicEventBus()
        router = BusRouter(public_bus=bus, ttl_seconds=60, gc_interval=60)
        p1 = router.get_or_create("s1")
        p2 = router.get_or_create("s1")
        assert p1 is p2  # 同一实例

    async def test_destroy(self):
        bus = PublicEventBus()
        router = BusRouter(public_bus=bus, ttl_seconds=60, gc_interval=60)
        router.get_or_create("s1")
        await router.destroy("s1")
        assert router.get("s1") is None

    async def test_worker_factory_called(self):
        bus = PublicEventBus()
        router = BusRouter(public_bus=bus, ttl_seconds=60, gc_interval=60)
        factory_calls = []

        async def factory(sid, priv_bus):
            factory_calls.append(sid)

        router.register_worker_factory(factory)
        await router.start()
        # 等待路由循环订阅完毕
        await asyncio.sleep(0.05)

        await bus.publish(EventEnvelope(
            type=USER_INPUT, session_id="fac_s",
            source="test", payload={"content": "hi"},
        ))
        # 等待路由循环处理事件
        for _ in range(10):
            await asyncio.sleep(0.05)
            if "fac_s" in factory_calls:
                break

        assert "fac_s" in factory_calls
        await router.stop()

    async def test_on_destroy_callback(self):
        bus = PublicEventBus()
        router = BusRouter(public_bus=bus, ttl_seconds=60, gc_interval=60)
        destroyed = []

        async def on_destroy(sid):
            destroyed.append(sid)

        router.on_destroy(on_destroy)
        router.get_or_create("ds")
        await router.destroy("ds")
        assert "ds" in destroyed

    async def test_touch(self):
        bus = PublicEventBus()
        router = BusRouter(public_bus=bus, ttl_seconds=60, gc_interval=60)
        router.get_or_create("touch_s")
        import time
        old_time = router._last_active["touch_s"]
        await asyncio.sleep(0.01)
        router.touch("touch_s")
        assert router._last_active["touch_s"] >= old_time

    async def test_non_user_input_no_create(self):
        """非 USER_INPUT 事件不应创建私有总线"""
        bus = PublicEventBus()
        router = BusRouter(public_bus=bus, ttl_seconds=60, gc_interval=60)
        await router.start()

        await bus.publish(EventEnvelope(
            type="agent.step_completed", session_id="no_create",
            source="test",
        ))
        await asyncio.sleep(0.1)
        assert router.get("no_create") is None

        await router.stop()
