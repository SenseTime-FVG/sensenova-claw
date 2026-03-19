from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest

from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import AGENT_STEP_COMPLETED, USER_INPUT
from agentos.adapters.channels.base import Channel
from agentos.interfaces.ws.gateway import Gateway
from agentos.kernel.runtime.publisher import EventPublisher


class MockChannel(Channel):
    """Mock Channel for testing"""

    def __init__(self, channel_id: str):
        self._channel_id = channel_id
        self.received_events: list[EventEnvelope] = []
        self.started = False
        self.stopped = False

    def get_channel_id(self) -> str:
        return self._channel_id

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def send_event(self, event: EventEnvelope) -> None:
        self.received_events.append(event)


class _RepoWithMeta:
    def __init__(self, meta_by_session: dict[str, dict[str, Any] | None]):
        self._meta_by_session = meta_by_session

    async def get_session_meta(self, session_id: str) -> dict[str, Any] | None:
        return self._meta_by_session.get(session_id)


@pytest.mark.asyncio
async def test_gateway_register_channel():
    """测试注册 Channel"""
    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    channel = MockChannel("test-channel")
    gateway.register_channel(channel)

    assert "test-channel" in gateway._channels


@pytest.mark.asyncio
async def test_gateway_bind_session():
    """测试绑定 session"""
    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    session_id = "sess_123"
    channel_id = "test-channel"

    gateway.bind_session(session_id, channel_id)
    assert gateway._session_bindings[session_id] == channel_id

    gateway.unbind_session(session_id)
    assert session_id not in gateway._session_bindings


@pytest.mark.asyncio
async def test_gateway_dispatch_event():
    """测试事件分发"""
    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    channel = MockChannel("test-channel")
    gateway.register_channel(channel)

    session_id = "sess_123"
    gateway.bind_session(session_id, "test-channel")

    await gateway.start()
    await asyncio.sleep(0.1)

    event = EventEnvelope(
        type=AGENT_STEP_COMPLETED,
        session_id=session_id,
        source="test",
        payload={"result": {"content": "test response"}},
    )

    await publisher.publish(event)
    await asyncio.sleep(0.2)

    await gateway.stop()

    assert len(channel.received_events) > 0
    assert channel.received_events[0].session_id == session_id


@pytest.mark.asyncio
async def test_gateway_publish_from_channel():
    """测试从 Channel 发布事件"""
    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    collected: list[EventEnvelope] = []

    async def collector():
        async for event in bus.subscribe():
            collected.append(event)
            if len(collected) >= 1:
                break

    collect_task = asyncio.create_task(collector())
    await asyncio.sleep(0.1)

    event = EventEnvelope(
        type=USER_INPUT,
        session_id="sess_123",
        source="channel",
        payload={"content": "test"},
    )

    await gateway.publish_from_channel(event)
    await asyncio.wait_for(collect_task, timeout=1)

    assert len(collected) == 1
    assert collected[0].type == USER_INPUT


@pytest.mark.asyncio
async def test_gateway_dispatch_event_inherits_channel_binding_from_parent():
    """子会话未绑定时，应继承父会话的 channel 绑定并缓存。"""
    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    repo = _RepoWithMeta(
        {
            "child_sess": {"parent_session_id": "parent_sess"},
            "parent_sess": {"agent_id": "default"},
        }
    )
    gateway = Gateway(publisher=publisher, repo=repo)

    channel = MockChannel("websocket")
    gateway.register_channel(channel)
    gateway.bind_session("parent_sess", "websocket")

    event = EventEnvelope(
        type=AGENT_STEP_COMPLETED,
        session_id="child_sess",
        source="test",
        payload={"result": {"content": "ok"}},
    )
    await gateway._dispatch_event(event)

    assert len(channel.received_events) == 1
    assert channel.received_events[0].session_id == "child_sess"
    assert gateway._session_bindings.get("child_sess") == "websocket"


@pytest.mark.asyncio
async def test_gateway_dispatch_event_without_parent_binding_is_dropped():
    """父链路无绑定时，事件不应误投递。"""
    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    repo = _RepoWithMeta(
        {
            "child_sess": {"parent_session_id": "parent_sess"},
            "parent_sess": {"agent_id": "default"},
        }
    )
    gateway = Gateway(publisher=publisher, repo=repo)

    channel = MockChannel("websocket")
    gateway.register_channel(channel)

    event = EventEnvelope(
        type=AGENT_STEP_COMPLETED,
        session_id="child_sess",
        source="test",
        payload={"result": {"content": "no-route"}},
    )
    await gateway._dispatch_event(event)

    assert len(channel.received_events) == 0
    assert "child_sess" not in gateway._session_bindings


@pytest.mark.asyncio
async def test_gateway_dispatch_event_parent_loop_is_safe():
    """父会话链路出现环时应安全退出，不应死循环。"""
    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    repo = _RepoWithMeta(
        {
            "sess_a": {"parent_session_id": "sess_b"},
            "sess_b": {"parent_session_id": "sess_a"},
        }
    )
    gateway = Gateway(publisher=publisher, repo=repo)
    channel = MockChannel("websocket")
    gateway.register_channel(channel)

    event = EventEnvelope(
        type=AGENT_STEP_COMPLETED,
        session_id="sess_a",
        source="test",
        payload={"result": {"content": "loop"}},
    )
    await gateway._dispatch_event(event)

    assert len(channel.received_events) == 0
    assert "sess_a" not in gateway._session_bindings
