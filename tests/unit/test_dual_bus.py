"""双总线架构单元测试"""
from __future__ import annotations

import asyncio
import uuid

import pytest

from sensenova_claw.kernel.events.bus import PrivateEventBus, PublicEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.router import BusRouter
from sensenova_claw.kernel.events.types import (
    AGENT_STEP_COMPLETED,
    AGENT_STEP_STARTED,
    LLM_CALL_REQUESTED,
    USER_INPUT,
)


# ---------- PrivateEventBus ----------


@pytest.mark.asyncio
async def test_private_bus_publish_flows_back_to_public():
    """PrivateEventBus.publish 应回流到 PublicEventBus"""
    public = PublicEventBus()
    private = PrivateEventBus(session_id="sess_1", public_bus=public)

    public_collected: list[EventEnvelope] = []

    async def public_collector():
        async for event in public.subscribe():
            public_collected.append(event)
            if len(public_collected) >= 1:
                break

    collect_task = asyncio.create_task(public_collector())
    await asyncio.sleep(0.05)

    event = EventEnvelope(
        type=AGENT_STEP_STARTED,
        session_id="sess_1",
        source="agent",
        payload={"test": True},
    )
    await private.publish(event)
    await asyncio.wait_for(collect_task, timeout=1)

    assert len(public_collected) == 1
    assert public_collected[0].type == AGENT_STEP_STARTED


@pytest.mark.asyncio
async def test_private_bus_deliver_does_not_flow_back():
    """PrivateEventBus.deliver 不应回流到 PublicEventBus"""
    public = PublicEventBus()
    private = PrivateEventBus(session_id="sess_1", public_bus=public)

    public_collected: list[EventEnvelope] = []
    private_collected: list[EventEnvelope] = []

    async def public_collector():
        async for event in public.subscribe():
            public_collected.append(event)

    async def private_collector():
        async for event in private.subscribe():
            private_collected.append(event)
            if len(private_collected) >= 1:
                break

    pub_task = asyncio.create_task(public_collector())
    priv_task = asyncio.create_task(private_collector())
    await asyncio.sleep(0.05)

    event = EventEnvelope(
        type=AGENT_STEP_STARTED,
        session_id="sess_1",
        source="agent",
        payload={"test": True},
    )
    await private.deliver(event)
    await asyncio.wait_for(priv_task, timeout=1)

    # 私有订阅者收到
    assert len(private_collected) == 1
    # 公共总线不应收到
    assert len(public_collected) == 0

    pub_task.cancel()
    try:
        await pub_task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_private_bus_publish_delivers_to_private_subscribers():
    """PrivateEventBus.publish 应同时分发给私有订阅者"""
    public = PublicEventBus()
    private = PrivateEventBus(session_id="sess_1", public_bus=public)

    private_collected: list[EventEnvelope] = []

    async def private_collector():
        async for event in private.subscribe():
            private_collected.append(event)
            if len(private_collected) >= 1:
                break

    collect_task = asyncio.create_task(private_collector())
    await asyncio.sleep(0.05)

    event = EventEnvelope(
        type=LLM_CALL_REQUESTED,
        session_id="sess_1",
        source="agent",
        payload={},
    )
    await private.publish(event)
    await asyncio.wait_for(collect_task, timeout=1)

    assert len(private_collected) == 1
    assert private_collected[0].type == LLM_CALL_REQUESTED


# ---------- BusRouter ----------


@pytest.mark.asyncio
async def test_bus_router_lazy_creation():
    """BusRouter.get_or_create 惰性创建 PrivateEventBus"""
    public = PublicEventBus()
    router = BusRouter(public_bus=public, ttl_seconds=3600, gc_interval=60)

    assert router.get("sess_1") is None

    bus = router.get_or_create("sess_1")
    assert bus is not None
    assert bus.session_id == "sess_1"

    # 再次获取应返回同一实例
    bus2 = router.get_or_create("sess_1")
    assert bus is bus2

    await router.stop()


@pytest.mark.asyncio
async def test_bus_router_destroy():
    """BusRouter.destroy 销毁并通知回调"""
    public = PublicEventBus()
    router = BusRouter(public_bus=public, ttl_seconds=3600, gc_interval=60)

    destroyed_sessions: list[str] = []

    async def on_destroy(session_id: str):
        destroyed_sessions.append(session_id)

    router.on_destroy(on_destroy)
    router.get_or_create("sess_1")

    await router.destroy("sess_1")

    assert router.get("sess_1") is None
    assert "sess_1" in destroyed_sessions

    await router.stop()


@pytest.mark.asyncio
async def test_bus_router_routes_events_to_private_bus():
    """BusRouter 将 PublicEventBus 上的事件路由到对应 PrivateEventBus"""
    public = PublicEventBus()
    router = BusRouter(public_bus=public, ttl_seconds=3600, gc_interval=60)

    # 注册一个 Worker 工厂（空操作，只是创建 Worker 的占位）
    factory_calls: list[str] = []

    async def mock_factory(session_id: str, private_bus: PrivateEventBus):
        factory_calls.append(session_id)

    router.register_worker_factory(mock_factory)

    await router.start()
    await asyncio.sleep(0.05)

    session_id = "sess_test_route"

    # 发布 USER_INPUT 到公共总线 → BusRouter 应创建 PrivateEventBus 并路由
    event = EventEnvelope(
        type=USER_INPUT,
        session_id=session_id,
        source="websocket",
        payload={"content": "hello"},
    )
    await public.publish(event)
    await asyncio.sleep(0.2)

    # 工厂应被调用
    assert session_id in factory_calls

    # 私有总线应存在
    private = router.get(session_id)
    assert private is not None

    await router.stop()


@pytest.mark.asyncio
async def test_bus_router_worker_factory_called_on_first_event():
    """BusRouter 首次遇到 session 的 USER_INPUT 时调用所有注册的工厂"""
    public = PublicEventBus()
    router = BusRouter(public_bus=public, ttl_seconds=3600, gc_interval=60)

    factory1_calls: list[str] = []
    factory2_calls: list[str] = []

    async def factory1(session_id: str, private_bus: PrivateEventBus):
        factory1_calls.append(session_id)

    async def factory2(session_id: str, private_bus: PrivateEventBus):
        factory2_calls.append(session_id)

    router.register_worker_factory(factory1)
    router.register_worker_factory(factory2)

    await router.start()
    await asyncio.sleep(0.05)

    await public.publish(EventEnvelope(
        type=USER_INPUT,
        session_id="sess_a",
        source="websocket",
        payload={"content": "test"},
    ))
    await asyncio.sleep(0.2)

    assert "sess_a" in factory1_calls
    assert "sess_a" in factory2_calls

    # 第二次不应再调用工厂
    factory1_calls.clear()
    factory2_calls.clear()

    await public.publish(EventEnvelope(
        type=USER_INPUT,
        session_id="sess_a",
        source="websocket",
        payload={"content": "test2"},
    ))
    await asyncio.sleep(0.2)

    assert len(factory1_calls) == 0
    assert len(factory2_calls) == 0

    await router.stop()


# ---------- 会话隔离 ----------


@pytest.mark.asyncio
async def test_session_isolation():
    """两个 session 的事件互不干扰"""
    public = PublicEventBus()
    router = BusRouter(public_bus=public, ttl_seconds=3600, gc_interval=60)

    session_a_events: list[EventEnvelope] = []
    session_b_events: list[EventEnvelope] = []

    async def factory(session_id: str, private_bus: PrivateEventBus):
        # 为每个 session 启动一个收集器
        async def collector():
            async for event in private_bus.subscribe():
                if session_id == "sess_a":
                    session_a_events.append(event)
                else:
                    session_b_events.append(event)

        asyncio.create_task(collector())

    router.register_worker_factory(factory)

    await router.start()
    await asyncio.sleep(0.05)

    # 创建 session A
    await public.publish(EventEnvelope(
        type=USER_INPUT,
        session_id="sess_a",
        source="websocket",
        payload={"content": "hello A"},
    ))
    await asyncio.sleep(0.1)

    # 创建 session B
    await public.publish(EventEnvelope(
        type=USER_INPUT,
        session_id="sess_b",
        source="websocket",
        payload={"content": "hello B"},
    ))
    await asyncio.sleep(0.1)

    # 发一个只属于 session A 的事件
    await public.publish(EventEnvelope(
        type=AGENT_STEP_STARTED,
        session_id="sess_a",
        source="agent",
        payload={"step": 1},
    ))
    await asyncio.sleep(0.1)

    # session B 不应收到 session A 的 AGENT_STEP_STARTED 事件
    b_types = [e.type for e in session_b_events]
    assert AGENT_STEP_STARTED not in b_types

    # session A 应收到自己的事件
    a_types = [e.type for e in session_a_events]
    assert USER_INPUT in a_types
    assert AGENT_STEP_STARTED in a_types

    await router.stop()


# ---------- 去重 ----------


@pytest.mark.asyncio
async def test_no_duplicate_delivery_to_workers():
    """Worker 从 PrivateEventBus 发布事件后，不应再被 BusRouter 重复投递"""
    public = PublicEventBus()
    router = BusRouter(public_bus=public, ttl_seconds=3600, gc_interval=9999)

    worker_events: list[EventEnvelope] = []

    async def factory(session_id: str, private_bus: PrivateEventBus):
        async def worker_loop():
            async for event in private_bus.subscribe():
                worker_events.append(event)
        asyncio.create_task(worker_loop())

    router.register_worker_factory(factory)
    await router.start()
    await asyncio.sleep(0.05)

    # 1. 外部发布 USER_INPUT → BusRouter 创建 PrivateEventBus + Worker → deliver
    await public.publish(EventEnvelope(
        type=USER_INPUT,
        session_id="sess_dedup",
        source="websocket",
        payload={"content": "hello"},
    ))
    await asyncio.sleep(0.1)

    assert len([e for e in worker_events if e.type == USER_INPUT]) == 1

    # 2. 模拟 Worker 在 PrivateEventBus 上 publish 事件
    private_bus = router.get("sess_dedup")
    assert private_bus is not None

    await private_bus.publish(EventEnvelope(
        type=AGENT_STEP_STARTED,
        session_id="sess_dedup",
        source="agent",
        payload={"step": 1},
    ))
    await asyncio.sleep(0.1)

    # Worker 应该只收到 1 次 AGENT_STEP_STARTED（来自 PrivateEventBus.publish 的直接投递）
    step_events = [e for e in worker_events if e.type == AGENT_STEP_STARTED]
    assert len(step_events) == 1, f"期望 1 次，实际 {len(step_events)} 次"

    await router.stop()


# ---------- GC ----------


@pytest.mark.asyncio
async def test_gc_cleans_expired_sessions():
    """GC 应清理超时的 session"""
    public = PublicEventBus()
    # TTL=0.1s，GC 间隔=0.1s
    router = BusRouter(public_bus=public, ttl_seconds=0.1, gc_interval=0.1)

    destroyed: list[str] = []

    async def on_destroy(session_id: str):
        destroyed.append(session_id)

    router.on_destroy(on_destroy)

    async def noop_factory(session_id: str, private_bus: PrivateEventBus):
        pass

    router.register_worker_factory(noop_factory)

    await router.start()
    await asyncio.sleep(0.05)

    # 创建 session
    await public.publish(EventEnvelope(
        type=USER_INPUT,
        session_id="sess_gc",
        source="websocket",
        payload={"content": "test"},
    ))
    await asyncio.sleep(0.05)

    # 验证私有总线存在（不使用 get() 因为它会刷新活跃时间）
    assert "sess_gc" in router._private_buses

    # 等待 GC 触发（TTL 0.1s + GC 间隔 0.1s）
    await asyncio.sleep(0.4)

    assert "sess_gc" in destroyed
    assert "sess_gc" not in router._private_buses

    await router.stop()
