"""WhatsApp Channel 单元测试。"""

from __future__ import annotations

import asyncio

import pytest

from sensenova_claw.adapters.plugins.whatsapp.bridge_client import SidecarBridgeClient
from sensenova_claw.adapters.plugins.whatsapp.channel import WhatsAppChannel
from sensenova_claw.adapters.plugins.whatsapp.config import WhatsAppConfig
from sensenova_claw.adapters.plugins.whatsapp.models import WhatsAppInboundMessage
from sensenova_claw.interfaces.ws.gateway import Gateway
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import (
    AGENT_STEP_COMPLETED,
    ERROR_RAISED,
    TOOL_CALL_STARTED,
    USER_INPUT,
    USER_QUESTION_ANSWERED,
    USER_QUESTION_ASKED,
)
from sensenova_claw.kernel.runtime.publisher import EventPublisher


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
        self.event_handler = None
        self.sent_messages: list[dict] = []

    def set_message_handler(self, handler) -> None:
        self.handler = handler

    def set_event_handler(self, handler) -> None:
        self.event_handler = handler

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def send_text(self, target: str, text: str) -> dict:
        self.sent_messages.append({"target": target, "text": text})
        return {"success": True, "message_id": f"msg:{target}"}


class _TimeoutOnStartBridge(_FakeWhatsAppBridge):
    async def start(self) -> None:
        self.started = True
        raise TimeoutError("WhatsApp sidecar command timed out: start")


class _TimeoutAfterDebugBridge(_FakeWhatsAppBridge):
    async def start(self) -> None:
        self.started = True
        assert self.event_handler is not None
        await self.event_handler(
            {
                "type": "debug",
                "payload": {
                    "message": "auth state loaded",
                },
            }
        )
        raise TimeoutError("WhatsApp sidecar command timed out: start")


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
        auth_dir="/tmp/sensenova_claw-whatsapp-auth",
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
            config=WhatsAppConfig(enabled=True, auth_dir="/tmp/sensenova_claw-whatsapp-auth"),
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

    @pytest.mark.asyncio
    async def test_start_timeout_does_not_crash_channel_startup(self):
        bus = PublicEventBus()
        publisher = EventPublisher(bus=bus)
        gateway = Gateway(publisher=publisher)
        bridge = _TimeoutOnStartBridge()
        channel = WhatsAppChannel(
            config=WhatsAppConfig(enabled=True, auth_dir="/tmp/sensenova_claw-whatsapp-auth"),
            plugin_api=_SimplePluginApi(gateway=gateway),
            bridge=bridge,
        )

        await channel.start()

        assert bridge.started is True
        assert channel._runtime_state.connected is False
        assert channel._runtime_state.state == "error"
        assert channel._runtime_state.last_error == "WhatsApp sidecar command timed out: start"

    @pytest.mark.asyncio
    async def test_start_timeout_preserves_last_bridge_debug_message(self):
        bus = PublicEventBus()
        publisher = EventPublisher(bus=bus)
        gateway = Gateway(publisher=publisher)
        bridge = _TimeoutAfterDebugBridge()
        channel = WhatsAppChannel(
            config=WhatsAppConfig(enabled=True, auth_dir="/tmp/sensenova_claw-whatsapp-auth"),
            plugin_api=_SimplePluginApi(gateway=gateway),
            bridge=bridge,
        )

        await channel.start()

        assert bridge.started is True
        assert channel._runtime_state.state == "error"
        assert channel._runtime_state.last_error == "WhatsApp sidecar command timed out: start"
        assert channel._runtime_state.debug_message == "auth state loaded"


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

    @pytest.mark.asyncio
    async def test_answers_pending_question_before_user_input(self):
        channel, _, bus, bridge = _make_channel()
        session_id = "whatsapp_ask_001"
        channel._chat_sessions["dm:+15550000001"] = session_id
        channel._session_meta[session_id] = channel._session_meta_model(
            chat_jid="15550000001@s.whatsapp.net",
            chat_type="p2p",
            sender_jid="15550000001@s.whatsapp.net",
            last_message_id="wamid-0",
        )

        await channel.send_event(
            EventEnvelope(
                type=USER_QUESTION_ASKED,
                session_id=session_id,
                source="tool",
                payload={"question_id": "q_wa_1", "question": "请选择环境"},
            )
        )
        assert bridge.sent_messages[-1]["text"] == "请选择环境"

        async def collect():
            async for event in bus.subscribe():
                if event.type == USER_QUESTION_ANSWERED:
                    return event

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.05)

        await channel.handle_incoming_message(
            WhatsAppInboundMessage(
                text="生产环境",
                chat_jid="15550000001@s.whatsapp.net",
                chat_type="p2p",
                sender_jid="15550000001@s.whatsapp.net",
                message_id="wamid-1",
            )
        )

        event = await asyncio.wait_for(task, timeout=2)
        assert event.type == USER_QUESTION_ANSWERED
        assert event.payload["question_id"] == "q_wa_1"
        assert event.payload["answer"] == "生产环境"

    @pytest.mark.asyncio
    async def test_restores_user_input_after_answering_pending_question(self):
        channel, _, bus, _ = _make_channel()
        session_id = "whatsapp_ask_002"
        channel._chat_sessions["dm:+15550000002"] = session_id
        channel._session_meta[session_id] = channel._session_meta_model(
            chat_jid="15550000002@s.whatsapp.net",
            chat_type="p2p",
            sender_jid="15550000002@s.whatsapp.net",
            last_message_id="wamid-0",
        )
        await channel.send_event(
            EventEnvelope(
                type=USER_QUESTION_ASKED,
                session_id=session_id,
                source="tool",
                payload={"question_id": "q_wa_2", "question": "补充说明"},
            )
        )

        async def collect_answer():
            async for event in bus.subscribe():
                if event.type == USER_QUESTION_ANSWERED:
                    return event

        answer_task = asyncio.create_task(collect_answer())
        await asyncio.sleep(0.05)
        await channel.handle_incoming_message(
            WhatsAppInboundMessage(
                text="第一次回答",
                chat_jid="15550000002@s.whatsapp.net",
                chat_type="p2p",
                sender_jid="15550000002@s.whatsapp.net",
                message_id="wamid-a",
            )
        )
        first_event = await asyncio.wait_for(answer_task, timeout=2)
        assert first_event.type == USER_QUESTION_ANSWERED

        async def collect_input():
            async for event in bus.subscribe():
                if event.type == USER_INPUT:
                    return event

        input_task = asyncio.create_task(collect_input())
        await asyncio.sleep(0.05)
        await channel.handle_incoming_message(
            WhatsAppInboundMessage(
                text="新的普通消息",
                chat_jid="15550000002@s.whatsapp.net",
                chat_type="p2p",
                sender_jid="15550000002@s.whatsapp.net",
                message_id="wamid-b",
            )
        )
        second_event = await asyncio.wait_for(input_task, timeout=2)
        assert second_event.type == USER_INPUT
        assert second_event.payload["content"] == "新的普通消息"


class TestOutbound:
    @pytest.mark.asyncio
    async def test_send_event_forwards_user_question_asked(self):
        channel, _, _, bridge = _make_channel()
        channel._session_meta["whatsapp_001"] = channel._session_meta_model(
            chat_jid="15550000001@s.whatsapp.net",
            chat_type="p2p",
            sender_jid="15550000001@s.whatsapp.net",
            last_message_id="wamid-1",
        )

        await channel.send_event(
            EventEnvelope(
                type=USER_QUESTION_ASKED,
                session_id="whatsapp_001",
                source="tool",
                payload={"question": "请补充更多上下文"},
            )
        )

        assert bridge.sent_messages[-1]["target"] == "15550000001@s.whatsapp.net"
        assert bridge.sent_messages[-1]["text"] == "请补充更多上下文"

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
