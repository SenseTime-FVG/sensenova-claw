"""WhatsApp Channel 单元测试。"""

from __future__ import annotations

import asyncio

import pytest

from agentos.adapters.plugins.whatsapp.bridge_client import SidecarBridgeClient
from agentos.adapters.plugins.whatsapp.channel import WhatsAppChannel
from agentos.adapters.plugins.whatsapp.config import WhatsAppConfig
from agentos.adapters.plugins.whatsapp.models import WhatsAppInboundMessage
from agentos.interfaces.ws.gateway import Gateway
from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import AGENT_STEP_COMPLETED, ERROR_RAISED, TOOL_CALL_STARTED, USER_INPUT
from agentos.kernel.runtime.publisher import EventPublisher


class _SimplePluginApi:
    def __init__(self, gateway: Gateway):
        self._gateway = gateway

    def get_gateway(self) -> Gateway:
        return self._gateway


class _FakeWhatsAppBridge:
    def __init__(self):
        self.started = False
        self.stopped = False
        self.handler = None
        self.sent_messages: list[dict] = []

    def set_message_handler(self, handler) -> None:
        self.handler = handler

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
    bridge = _FakeWhatsAppBridge()
    config = WhatsAppConfig(
        enabled=True,
        auth_dir="/tmp/agentos-whatsapp-auth",
        dm_policy=dm_policy,
        group_policy=group_policy,
        allowlist=allowlist or [],
        group_allowlist=group_allowlist or [],
    )
    channel = WhatsAppChannel(
        config=config,
        plugin_api=_SimplePluginApi(gateway=gateway),
        bridge=bridge,
    )
    return channel, gateway, bus, bridge


class TestLifecycle:
    def test_default_bridge_uses_sidecar_client(self):
        bus = PublicEventBus()
        publisher = EventPublisher(bus=bus)
        gateway = Gateway(publisher=publisher)
        channel = WhatsAppChannel(
            config=WhatsAppConfig(enabled=True, auth_dir="/tmp/agentos-whatsapp-auth"),
            plugin_api=_SimplePluginApi(gateway=gateway),
        )
        assert isinstance(channel._bridge, SidecarBridgeClient)

    @pytest.mark.asyncio
    async def test_start_and_stop_delegate_to_bridge(self):
        channel, _, _, bridge = _make_channel()
        await channel.start()
        await channel.stop()
        assert bridge.started is True
        assert bridge.stopped is True
        assert bridge.handler is not None


class TestShouldRespond:
    def test_p2p_open_policy(self):
        channel, _, _, _ = _make_channel(dm_policy="open")
        assert channel._should_respond("p2p", "15550000001@s.whatsapp.net", "15550000001@s.whatsapp.net") is True

    def test_p2p_allowlist_miss(self):
        channel, _, _, _ = _make_channel(dm_policy="allowlist", allowlist=["+15550000002"])
        assert channel._should_respond("p2p", "15550000001@s.whatsapp.net", "15550000001@s.whatsapp.net") is False

    def test_group_allowlist_hit(self):
        channel, _, _, _ = _make_channel(group_policy="allowlist", group_allowlist=["1203630@g.us"])
        assert channel._should_respond("group", "15550000001@s.whatsapp.net", "1203630@g.us") is True

    def test_group_allowlist_miss(self):
        channel, _, _, _ = _make_channel(group_policy="allowlist", group_allowlist=["1203630@g.us"])
        assert channel._should_respond("group", "15550000001@s.whatsapp.net", "1203631@g.us") is False


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

        await channel.handle_incoming_message(
            WhatsAppInboundMessage(
                text="你好",
                chat_jid="15550000001@s.whatsapp.net",
                chat_type="p2p",
                sender_jid="15550000001@s.whatsapp.net",
                message_id="wamid-1",
            )
        )

        await asyncio.wait_for(task, timeout=2)

        assert len(gateway._session_bindings) == 1
        session_id = next(iter(gateway._session_bindings))
        assert gateway._session_bindings[session_id] == "whatsapp"
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

        await channel.handle_incoming_message(
            WhatsAppInboundMessage(
                text="first",
                chat_jid="15550000001@s.whatsapp.net",
                chat_type="p2p",
                sender_jid="15550000001@s.whatsapp.net",
                message_id="wamid-1",
            )
        )
        await channel.handle_incoming_message(
            WhatsAppInboundMessage(
                text="second",
                chat_jid="15550009999@s.whatsapp.net",
                chat_type="p2p",
                sender_jid="15550000001@s.whatsapp.net",
                message_id="wamid-2",
            )
        )

        await asyncio.wait_for(task, timeout=2)
        assert collected[0].session_id == collected[1].session_id

    @pytest.mark.asyncio
    async def test_blocked_message_is_ignored(self):
        channel, gateway, bus, _ = _make_channel(
            dm_policy="allowlist",
            allowlist=["+15550000002"],
        )
        collected: list[EventEnvelope] = []

        async def collect():
            async for event in bus.subscribe():
                collected.append(event)
                break

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.05)

        await channel.handle_incoming_message(
            WhatsAppInboundMessage(
                text="hello",
                chat_jid="15550000001@s.whatsapp.net",
                chat_type="p2p",
                sender_jid="15550000001@s.whatsapp.net",
                message_id="wamid-1",
            )
        )

        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert collected == []
        assert gateway._session_bindings == {}


class TestOutbound:
    @pytest.mark.asyncio
    async def test_send_event_replies_to_known_session(self):
        channel, _, _, bridge = _make_channel()
        channel._session_meta["whatsapp_001"] = channel._session_meta_model(
            chat_jid="15550000001@s.whatsapp.net",
            chat_type="p2p",
            sender_jid="15550000001@s.whatsapp.net",
            last_message_id="wamid-1",
        )

        await channel.send_event(
            EventEnvelope(
                type=AGENT_STEP_COMPLETED,
                session_id="whatsapp_001",
                source="agent",
                payload={"final_response": "这是回复"},
            )
        )

        assert bridge.sent_messages[-1]["target"] == "15550000001@s.whatsapp.net"
        assert bridge.sent_messages[-1]["text"] == "这是回复"

    @pytest.mark.asyncio
    async def test_send_event_reports_error(self):
        channel, _, _, bridge = _make_channel()
        channel._session_meta["whatsapp_001"] = channel._session_meta_model(
            chat_jid="15550000001@s.whatsapp.net",
            chat_type="p2p",
            sender_jid="15550000001@s.whatsapp.net",
            last_message_id="wamid-1",
        )

        await channel.send_event(
            EventEnvelope(
                type=ERROR_RAISED,
                session_id="whatsapp_001",
                source="system",
                payload={"error_message": "失败了"},
            )
        )

        assert "失败了" in bridge.sent_messages[-1]["text"]

    @pytest.mark.asyncio
    async def test_send_event_reports_tool_progress_when_enabled(self):
        channel, _, _, bridge = _make_channel()
        channel._config.show_tool_progress = True
        channel._session_meta["whatsapp_001"] = channel._session_meta_model(
            chat_jid="15550000001@s.whatsapp.net",
            chat_type="p2p",
            sender_jid="15550000001@s.whatsapp.net",
            last_message_id="wamid-1",
        )

        await channel.send_event(
            EventEnvelope(
                type=TOOL_CALL_STARTED,
                session_id="whatsapp_001",
                source="system",
                payload={"tool_name": "serper_search"},
            )
        )

        assert "serper_search" in bridge.sent_messages[-1]["text"]

    @pytest.mark.asyncio
    async def test_send_outbound_delegates_to_bridge(self):
        channel, _, _, bridge = _make_channel()
        result = await channel.send_outbound(
            target="1203630@g.us",
            text="主动消息",
        )
        assert result["success"] is True
        assert bridge.sent_messages[-1]["target"] == "1203630@g.us"
        assert bridge.sent_messages[-1]["text"] == "主动消息"
