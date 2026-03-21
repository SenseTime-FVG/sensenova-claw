"""config.updated 事件常量和订阅者测试"""
import pytest
from agentos.kernel.events.types import CONFIG_UPDATED, SYSTEM_SESSION_ID


def test_config_updated_constant():
    assert CONFIG_UPDATED == "config.updated"


def test_system_session_id_constant():
    assert SYSTEM_SESSION_ID == "__system__"


import asyncio
from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.router import BusRouter


@pytest.mark.asyncio
async def test_bus_router_skips_config_events():
    """config.* 事件不应路由到私有总线"""
    bus = PublicEventBus()
    router = BusRouter(public_bus=bus)

    # 创建一个私有总线
    private_bus = router.get_or_create("test-session")
    delivered = []

    async def collect():
        async for event in private_bus.subscribe():
            delivered.append(event)

    task = asyncio.create_task(collect())
    await router.start()
    # 让 collect() 协程有机会开始执行并注册队列
    await asyncio.sleep(0)

    # 发布 config.updated 事件
    await bus.publish(EventEnvelope(
        type="config.updated",
        session_id="__system__",
        source="system",
        payload={"section": "llm", "changes": {}},
    ))

    # 发布一个普通事件到 test-session
    await bus.publish(EventEnvelope(
        type="user.input",
        session_id="test-session",
        payload={"text": "hello"},
    ))

    await asyncio.sleep(0.1)
    await router.stop()
    task.cancel()

    # 只应收到 user.input，不应收到 config.updated
    types = [e.type for e in delivered]
    assert "user.input" in types
    assert "config.updated" not in types
