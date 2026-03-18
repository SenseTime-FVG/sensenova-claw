"""Telegram Channel 单元测试。"""

from __future__ import annotations

import asyncio

import pytest

from agentos.adapters.channels.telegram.channel import TelegramChannel
from agentos.adapters.channels.telegram.config import TelegramConfig
from agentos.adapters.channels.telegram.models import TelegramInboundMessage
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


class _FakeTelegramRuntime:
    def __init__(self):
        self.started = False
        self.stopped = False
        self.handler = None
        self.bot_username = "agentos_bot"
        self.sent_messages: list[dict] = []

    def set_message_handler(self, handler) -> None:
        self.handler = handler

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def send_text(
        self,
        chat_id: str,
        text: str,
        *,
        reply_to_message_id: int | None = None,
        message_thread_id: int | None = None,
    ) -> dict:
        self.sent_messages.append(
            {
                "chat_id": chat_id,
                "text": text,
                "reply_to_message_id": reply_to_message_id,
                "message_thread_id": message_thread_id,
            }
        )
        return {"success": True, "message_id": f"msg:{chat_id}"}


def _make_channel(
    *,
    dm_policy: str = "open",
    group_policy: str = "allowlist",
    allowlist: list[str] | None = None,
    group_allowlist: list[str] | None = None,
    group_chat_allowlist: list[str] | None = None,
    require_mention: bool = True,
    reply_to_message: bool = True,
):
    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)
    runtime = _FakeTelegramRuntime()
    config = TelegramConfig(
        enabled=True,
        bot_token="123:abc",
        dm_policy=dm_policy,
        group_policy=group_policy,
        allowlist=allowlist or [],
        group_allowlist=group_allowlist or [],
        group_chat_allowlist=group_chat_allowlist or [],
        require_mention=require_mention,
        reply_to_message=reply_to_message,
    )
    channel = TelegramChannel(
        config=config,
        plugin_api=_SimplePluginApi(gateway=gateway),
        runtime=runtime,
    )
    return channel, gateway, bus, runtime


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_and_stop_delegate_to_runtime(self):
        channel, _, _, runtime = _make_channel()
        await channel.start()
        await channel.stop()
        assert runtime.started is True
        assert runtime.stopped is True
        assert runtime.handler is not None


class TestShouldRespond:
    def test_p2p_open_policy(self):
        channel, _, _, _ = _make_channel(dm_policy="open")
        assert channel._should_respond(
            TelegramInboundMessage(
                text="hello",
                chat_id="1001",
                chat_type="p2p",
                sender_id="1001",
                sender_username="alice",
                message_id=10,
            )
        ) is True

    def test_p2p_allowlist_miss(self):
        channel, _, _, _ = _make_channel(dm_policy="allowlist", allowlist=["2002"])
        assert channel._should_respond(
            TelegramInboundMessage(
                text="hello",
                chat_id="1001",
                chat_type="p2p",
                sender_id="1001",
                sender_username="alice",
                message_id=10,
            )
        ) is False

    def test_group_allowlist_hit(self):
        channel, _, _, _ = _make_channel(
            group_policy="allowlist",
            group_allowlist=["1001"],
            group_chat_allowlist=["-100123"],
        )
        assert channel._should_respond(
            TelegramInboundMessage(
                text="@agentos_bot hello",
                chat_id="-100123",
                chat_type="group",
                sender_id="1001",
                sender_username="alice",
                message_id=10,
                mentioned_bot=True,
            )
        ) is True

    def test_group_require_mention_blocks_message(self):
        channel, _, _, _ = _make_channel(
            group_policy="open",
            group_chat_allowlist=["-100123"],
            require_mention=True,
        )
        assert channel._should_respond(
            TelegramInboundMessage(
                text="hello",
                chat_id="-100123",
                chat_type="group",
                sender_id="1001",
                sender_username="alice",
                message_id=10,
                mentioned_bot=False,
            )
        ) is False


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
            TelegramInboundMessage(
                text="你好",
                chat_id="1001",
                chat_type="p2p",
                sender_id="1001",
                sender_username="alice",
                message_id=10,
            )
        )

        await asyncio.wait_for(task, timeout=2)
        assert len(gateway._session_bindings) == 1
        session_id = next(iter(gateway._session_bindings))
        assert gateway._session_bindings[session_id] == "telegram"
        assert collected[0].payload["content"] == "你好"
        assert collected[0].session_id == session_id

    @pytest.mark.asyncio
    async def test_reuses_topic_session_for_same_group_topic(self):
        channel, _, bus, _ = _make_channel(
            group_policy="open",
            group_chat_allowlist=["-100123"],
            require_mention=False,
        )
        collected: list[EventEnvelope] = []

        async def collect():
            async for event in bus.subscribe():
                collected.append(event)
                if len(collected) >= 2:
                    break

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.05)

        first = TelegramInboundMessage(
            text="first",
            chat_id="-100123",
            chat_type="group",
            sender_id="1001",
            sender_username="alice",
            message_id=11,
            message_thread_id=777,
            mentioned_bot=True,
        )
        second = TelegramInboundMessage(
            text="second",
            chat_id="-100123",
            chat_type="group",
            sender_id="2002",
            sender_username="bob",
            message_id=12,
            message_thread_id=777,
            mentioned_bot=True,
        )

        await channel.handle_incoming_message(first)
        await channel.handle_incoming_message(second)

        await asyncio.wait_for(task, timeout=2)
        assert collected[0].session_id == collected[1].session_id

    @pytest.mark.asyncio
    async def test_blocked_message_is_ignored(self):
        channel, gateway, bus, _ = _make_channel(
            group_policy="allowlist",
            group_allowlist=["2002"],
            group_chat_allowlist=["-100123"],
        )
        collected: list[EventEnvelope] = []

        async def collect():
            async for event in bus.subscribe():
                collected.append(event)
                break

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.05)

        await channel.handle_incoming_message(
            TelegramInboundMessage(
                text="@agentos_bot hello",
                chat_id="-100123",
                chat_type="group",
                sender_id="1001",
                sender_username="alice",
                message_id=10,
                mentioned_bot=True,
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
    async def test_send_event_replies_with_thread_and_reply_message(self):
        channel, _, _, runtime = _make_channel(
            group_policy="open",
            group_chat_allowlist=["-100123"],
        )
        channel._session_meta["telegram_001"] = channel._session_meta_model(
            chat_id="-100123",
            chat_type="group",
            sender_id="1001",
            sender_username="alice",
            last_message_id=10,
            message_thread_id=777,
        )

        await channel.send_event(
            EventEnvelope(
                type=AGENT_STEP_COMPLETED,
                session_id="telegram_001",
                source="agent",
                payload={"final_response": "这是回复"},
            )
        )

        assert runtime.sent_messages[-1]["chat_id"] == "-100123"
        assert runtime.sent_messages[-1]["text"] == "这是回复"
        assert runtime.sent_messages[-1]["reply_to_message_id"] == 10
        assert runtime.sent_messages[-1]["message_thread_id"] == 777

    @pytest.mark.asyncio
    async def test_send_event_reports_error(self):
        channel, _, _, runtime = _make_channel()
        channel._session_meta["telegram_001"] = channel._session_meta_model(
            chat_id="1001",
            chat_type="p2p",
            sender_id="1001",
            sender_username="alice",
            last_message_id=10,
        )

        await channel.send_event(
            EventEnvelope(
                type=ERROR_RAISED,
                session_id="telegram_001",
                source="system",
                payload={"error_message": "失败了"},
            )
        )

        assert "失败了" in runtime.sent_messages[-1]["text"]

    @pytest.mark.asyncio
    async def test_send_event_reports_tool_progress_when_enabled(self):
        channel, _, _, runtime = _make_channel()
        channel._config.show_tool_progress = True
        channel._session_meta["telegram_001"] = channel._session_meta_model(
            chat_id="1001",
            chat_type="p2p",
            sender_id="1001",
            sender_username="alice",
            last_message_id=10,
        )

        await channel.send_event(
            EventEnvelope(
                type=TOOL_CALL_STARTED,
                session_id="telegram_001",
                source="system",
                payload={"tool_name": "serper_search"},
            )
        )

        assert "serper_search" in runtime.sent_messages[-1]["text"]

    @pytest.mark.asyncio
    async def test_send_outbound_delegates_to_runtime(self):
        channel, _, _, runtime = _make_channel()
        result = await channel.send_outbound(target="-100123", text="主动消息")
        assert result["success"] is True
        assert runtime.sent_messages[-1]["chat_id"] == "-100123"
        assert runtime.sent_messages[-1]["text"] == "主动消息"
