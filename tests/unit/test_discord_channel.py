"""Discord Channel 单元测试。"""

from __future__ import annotations

import asyncio

import pytest

from sensenova_claw.adapters.plugins.discord.channel import DiscordChannel
from sensenova_claw.adapters.plugins.discord.config import DiscordConfig
from sensenova_claw.adapters.plugins.discord.models import DiscordInboundMessage
from sensenova_claw.interfaces.ws.gateway import Gateway
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import (
    AGENT_STEP_COMPLETED,
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


class _FakeDiscordRuntime:
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

    async def send_text(self, channel_id: str, text: str, *, message_reference: str | None = None) -> dict:
        self.sent_messages.append(
            {
                "channel_id": channel_id,
                "text": text,
                "message_reference": message_reference,
            }
        )
        return {"success": True, "message_id": f"msg:{channel_id}"}


def _make_channel(
    *,
    dm_policy: str = "open",
    group_policy: str = "allowlist",
    allowlist: list[str] | None = None,
    group_allowlist: list[str] | None = None,
    channel_allowlist: list[str] | None = None,
    require_mention: bool = True,
    reply_in_thread: bool = True,
    show_tool_progress: bool = False,
):
    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)
    runtime = _FakeDiscordRuntime()
    config = DiscordConfig(
        enabled=True,
        bot_token="discord-token",
        dm_policy=dm_policy,
        group_policy=group_policy,
        allowlist=allowlist or [],
        group_allowlist=group_allowlist or [],
        channel_allowlist=channel_allowlist or [],
        require_mention=require_mention,
        reply_in_thread=reply_in_thread,
        show_tool_progress=show_tool_progress,
    )
    channel = DiscordChannel(
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
    def test_dm_open_policy(self):
        channel, _, _, _ = _make_channel(dm_policy="open")
        assert channel._should_respond(
            DiscordInboundMessage(
                text="hello",
                channel_id="dm-1",
                channel_type="dm",
                sender_id="user-1",
                sender_name="alice",
                message_id="msg-1",
                mentioned_bot=False,
            )
        ) is True

    def test_group_require_mention_blocks_message(self):
        channel, _, _, _ = _make_channel(
            group_policy="open",
            channel_allowlist=["channel-1"],
            require_mention=True,
        )
        assert channel._should_respond(
            DiscordInboundMessage(
                text="hello",
                channel_id="channel-1",
                channel_type="group",
                sender_id="user-1",
                sender_name="alice",
                message_id="msg-1",
                guild_id="guild-1",
                mentioned_bot=False,
            )
        ) is False

    def test_thread_allowlist_hit(self):
        channel, _, _, _ = _make_channel(
            group_policy="allowlist",
            group_allowlist=["user-1"],
            channel_allowlist=["thread-1"],
            require_mention=False,
        )
        assert channel._should_respond(
            DiscordInboundMessage(
                text="hello",
                channel_id="thread-1",
                channel_type="thread",
                sender_id="user-1",
                sender_name="alice",
                message_id="msg-1",
                guild_id="guild-1",
                thread_id="thread-1",
                parent_channel_id="channel-1",
                mentioned_bot=False,
            )
        ) is True


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
            DiscordInboundMessage(
                text="你好",
                channel_id="dm-1",
                channel_type="dm",
                sender_id="user-1",
                sender_name="alice",
                message_id="msg-1",
                mentioned_bot=False,
            )
        )

        await asyncio.wait_for(task, timeout=2)
        assert len(gateway._session_bindings) == 1
        session_id = next(iter(gateway._session_bindings))
        assert gateway._session_bindings[session_id] == "discord"
        assert collected[0].payload["content"] == "你好"
        assert collected[0].session_id == session_id

    @pytest.mark.asyncio
    async def test_reuses_thread_session_for_same_thread(self):
        channel, _, bus, _ = _make_channel(
            group_policy="open",
            channel_allowlist=["thread-1"],
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

        first = DiscordInboundMessage(
            text="first",
            channel_id="thread-1",
            channel_type="thread",
            sender_id="user-1",
            sender_name="alice",
            message_id="msg-1",
            guild_id="guild-1",
            thread_id="thread-1",
            parent_channel_id="channel-1",
            mentioned_bot=True,
        )
        second = DiscordInboundMessage(
            text="second",
            channel_id="thread-1",
            channel_type="thread",
            sender_id="user-2",
            sender_name="bob",
            message_id="msg-2",
            guild_id="guild-1",
            thread_id="thread-1",
            parent_channel_id="channel-1",
            mentioned_bot=True,
        )

        await channel.handle_incoming_message(first)
        await channel.handle_incoming_message(second)

        await asyncio.wait_for(task, timeout=2)
        assert collected[0].session_id == collected[1].session_id

    @pytest.mark.asyncio
    async def test_answers_pending_question_before_user_input(self):
        channel, _, bus, runtime = _make_channel()
        session_id = "discord_ask_001"
        channel._chat_sessions["dm:user-1"] = session_id
        channel._session_meta[session_id] = channel._session_meta_model(
            channel_id="dm-1",
            channel_type="dm",
            sender_id="user-1",
            sender_name="alice",
            last_message_id="msg-0",
            guild_id=None,
            thread_id=None,
            parent_channel_id=None,
            reply_target_id="dm-1",
        )

        await channel.send_event(
            EventEnvelope(
                type=USER_QUESTION_ASKED,
                session_id=session_id,
                payload={"question_id": "q_discord_1", "question": "请选择环境"},
            )
        )
        assert runtime.sent_messages[-1]["text"] == "请选择环境"

        async def collect():
            async for event in bus.subscribe():
                if event.type == USER_QUESTION_ANSWERED:
                    return event

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.05)
        await channel.handle_incoming_message(
            DiscordInboundMessage(
                text="生产环境",
                channel_id="dm-1",
                channel_type="dm",
                sender_id="user-1",
                sender_name="alice",
                message_id="msg-1",
                mentioned_bot=False,
            )
        )
        event = await asyncio.wait_for(task, timeout=2)
        assert event.payload["question_id"] == "q_discord_1"
        assert event.payload["answer"] == "生产环境"


class TestOutbound:
    @pytest.mark.asyncio
    async def test_send_agent_reply_to_thread(self):
        channel, _, _, runtime = _make_channel(reply_in_thread=True)
        channel._session_meta["discord_001"] = channel._session_meta_model(
            channel_id="thread-1",
            channel_type="thread",
            sender_id="user-1",
            sender_name="alice",
            last_message_id="msg-1",
            guild_id="guild-1",
            thread_id="thread-1",
            parent_channel_id="channel-1",
            reply_target_id="thread-1",
        )

        await channel.send_event(
            EventEnvelope(
                type=AGENT_STEP_COMPLETED,
                session_id="discord_001",
                payload={"result": {"content": "已处理"}},
            )
        )

        assert runtime.sent_messages[-1]["channel_id"] == "thread-1"
        assert runtime.sent_messages[-1]["text"] == "已处理"

    @pytest.mark.asyncio
    async def test_tool_progress_message_uses_runtime(self):
        channel, _, _, runtime = _make_channel(show_tool_progress=True)
        channel._session_meta["discord_001"] = channel._session_meta_model(
            channel_id="channel-1",
            channel_type="group",
            sender_id="user-1",
            sender_name="alice",
            last_message_id="msg-1",
            guild_id="guild-1",
            thread_id=None,
            parent_channel_id=None,
            reply_target_id="channel-1",
        )

        await channel.send_event(
            EventEnvelope(
                type=TOOL_CALL_STARTED,
                session_id="discord_001",
                payload={"tool_name": "serper_search"},
            )
        )

        assert runtime.sent_messages[-1]["text"] == "正在执行 serper_search..."
