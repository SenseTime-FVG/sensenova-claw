"""企业微信 Channel 单元测试。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from agentos.adapters.channels.wecom.channel import WecomChannel
from agentos.adapters.channels.wecom.config import WecomConfig
from agentos.interfaces.ws.gateway import Gateway
from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import USER_INPUT
from agentos.kernel.runtime.publisher import EventPublisher


class _SimplePluginApi:
    def __init__(self, gateway: Gateway):
        self._gateway = gateway

    def get_gateway(self) -> Gateway:
        return self._gateway


class _FakeWecomClient:
    def __init__(self):
        self.sent_messages: list[dict] = []
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def send_text(self, target: str, text: str) -> dict:
        self.sent_messages.append({"target": target, "text": text})
        return {"success": True, "message_id": f"msg:{target}"}


def _make_channel(
    *,
    dm_policy: str = "open",
    group_policy: str = "open",
    allowlist: list[str] | None = None,
    group_allowlist: list[str] | None = None,
):
    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)
    client = _FakeWecomClient()
    config = WecomConfig(
        enabled=True,
        bot_id="bot_001",
        secret="secret_001",
        dm_policy=dm_policy,
        group_policy=group_policy,
        allowlist=allowlist or [],
        group_allowlist=group_allowlist or [],
    )
    channel = WecomChannel(
        config=config,
        plugin_api=_SimplePluginApi(gateway=gateway),
        client=client,
    )
    return channel, gateway, bus, client


class TestShouldRespond:
    def test_p2p_open_policy(self):
        channel, _, _, _ = _make_channel(dm_policy="open")
        assert channel._should_respond("p2p", "user-1", "chat-1") is True

    def test_p2p_allowlist_miss(self):
        channel, _, _, _ = _make_channel(dm_policy="allowlist", allowlist=["user-2"])
        assert channel._should_respond("p2p", "user-1", "chat-1") is False

    def test_group_allowlist_hit(self):
        channel, _, _, _ = _make_channel(
            group_policy="allowlist",
            group_allowlist=["group-1"],
        )
        assert channel._should_respond("group", "user-1", "group-1") is True

    def test_group_allowlist_miss(self):
        channel, _, _, _ = _make_channel(
            group_policy="allowlist",
            group_allowlist=["group-1"],
        )
        assert channel._should_respond("group", "user-1", "group-2") is False


class TestInbound:
    @pytest.mark.asyncio
    async def test_publishes_user_input_for_dm(self):
        channel, gateway, bus, _ = _make_channel()
        collected: list[EventEnvelope] = []

        async def collect():
            async for event in bus.subscribe():
                collected.append(event)
                if event.type == USER_INPUT:
                    break

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.05)

        await channel.handle_incoming_text(
            text="你好",
            chat_id="chat-1",
            chat_type="p2p",
            sender_id="user-1",
            message_id="msg-1",
        )

        await asyncio.wait_for(task, timeout=2)

        assert len(gateway._session_bindings) == 1
        session_id = next(iter(gateway._session_bindings))
        assert gateway._session_bindings[session_id] == "wecom"
        assert collected[0].payload["content"] == "你好"
        assert collected[0].session_id == session_id

    @pytest.mark.asyncio
    async def test_reuses_session_for_same_dm_sender(self):
        channel, _, bus, _ = _make_channel()
        collected: list[EventEnvelope] = []

        async def collect():
            async for event in bus.subscribe():
                collected.append(event)
                if len(collected) >= 2:
                    break

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.05)

        await channel.handle_incoming_text(
            text="first",
            chat_id="chat-a",
            chat_type="p2p",
            sender_id="user-1",
            message_id="msg-1",
        )
        await channel.handle_incoming_text(
            text="second",
            chat_id="chat-b",
            chat_type="p2p",
            sender_id="user-1",
            message_id="msg-2",
        )

        await asyncio.wait_for(task, timeout=2)
        assert collected[0].session_id == collected[1].session_id

    @pytest.mark.asyncio
    async def test_blocked_message_is_ignored(self):
        channel, gateway, bus, _ = _make_channel(
            dm_policy="allowlist",
            allowlist=["user-2"],
        )
        collected: list[EventEnvelope] = []

        async def collect():
            async for event in bus.subscribe():
                collected.append(event)
                break

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.05)

        await channel.handle_incoming_text(
            text="hello",
            chat_id="chat-a",
            chat_type="p2p",
            sender_id="user-1",
            message_id="msg-1",
        )

        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert collected == []
        assert gateway._session_bindings == {}
