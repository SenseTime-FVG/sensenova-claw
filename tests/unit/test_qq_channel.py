"""QQ Channel 单元测试。"""

from __future__ import annotations

import asyncio

import pytest

from sensenova_claw.adapters.plugins.qq.channel import QQChannel
from sensenova_claw.adapters.plugins.qq.config import QQConfig, QQOfficialConfig, QQOneBotConfig
from sensenova_claw.adapters.plugins.qq.models import QQInboundMessage
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


class _FakeQQRuntime:
    def __init__(self, mode: str = "onebot"):
        self.mode = mode
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

    async def send_text(self, target: str, text: str, *, reply_to_message_id: str | None = None) -> dict:
        self.sent_messages.append(
            {
                "target": target,
                "text": text,
                "reply_to_message_id": reply_to_message_id,
            }
        )
        return {"success": True, "message_id": f"msg:{target}"}


class _FailingQQRuntime(_FakeQQRuntime):
    async def start(self) -> None:
        self.started = True
        raise RuntimeError("qq auth failed")


def _make_config(
    *,
    mode: str = "onebot",
    dm_policy: str = "open",
    group_policy: str = "allowlist",
    allowlist: list[str] | None = None,
    group_allowlist: list[str] | None = None,
    require_mention: bool = True,
    reply_to_message: bool = True,
):
    return QQConfig(
        enabled=True,
        mode=mode,
        dm_policy=dm_policy,
        group_policy=group_policy,
        allowlist=allowlist or [],
        group_allowlist=group_allowlist or [],
        require_mention=require_mention,
        show_tool_progress=False,
        reply_to_message=reply_to_message,
        official=QQOfficialConfig(app_id="app", client_secret="secret"),
        onebot=QQOneBotConfig(ws_url="ws://127.0.0.1:3001"),
    )


def _make_channel(**config_kwargs):
    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)
    runtime = _FakeQQRuntime(mode=config_kwargs.get("mode", "onebot"))
    channel = QQChannel(
        config=_make_config(**config_kwargs),
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

    @pytest.mark.asyncio
    async def test_start_failure_marks_channel_failed(self):
        bus = PublicEventBus()
        publisher = EventPublisher(bus=bus)
        gateway = Gateway(publisher=publisher)
        runtime = _FailingQQRuntime()
        channel = QQChannel(
            config=_make_config(),
            plugin_api=_SimplePluginApi(gateway=gateway),
            runtime=runtime,
        )

        with pytest.raises(RuntimeError, match="qq auth failed"):
            await channel.start()

        assert channel._sensenova_claw_status == {"status": "failed", "error": "qq auth failed"}


class TestShouldRespond:
    def test_p2p_open_policy(self):
        channel, _, _, _ = _make_channel(dm_policy="open")
        assert channel._should_respond(
            QQInboundMessage(
                text="hello",
                chat_type="p2p",
                chat_id="1001",
                sender_id="1001",
                sender_name="alice",
                message_id="10",
                target="user:1001",
            )
        ) is True

    def test_p2p_allowlist_miss(self):
        channel, _, _, _ = _make_channel(dm_policy="allowlist", allowlist=["2002"])
        assert channel._should_respond(
            QQInboundMessage(
                text="hello",
                chat_type="p2p",
                chat_id="1001",
                sender_id="1001",
                sender_name="alice",
                message_id="10",
                target="user:1001",
            )
        ) is False

    def test_group_allowlist_hit(self):
        channel, _, _, _ = _make_channel(
            group_policy="allowlist",
            group_allowlist=["1001"],
            require_mention=False,
        )
        assert channel._should_respond(
            QQInboundMessage(
                text="@bot hello",
                chat_type="group",
                chat_id="group-1",
                sender_id="1001",
                sender_name="alice",
                message_id="10",
                target="group:group-1",
                mentioned_bot=True,
            )
        ) is True

    def test_group_require_mention_blocks_message(self):
        channel, _, _, _ = _make_channel(group_policy="open", require_mention=True)
        assert channel._should_respond(
            QQInboundMessage(
                text="hello",
                chat_type="group",
                chat_id="group-1",
                sender_id="1001",
                sender_name="alice",
                message_id="10",
                target="group:group-1",
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
            QQInboundMessage(
                text="你好",
                chat_type="p2p",
                chat_id="1001",
                sender_id="1001",
                sender_name="alice",
                message_id="10",
                target="user:1001",
            )
        )

        await asyncio.wait_for(task, timeout=2)
        assert len(gateway._session_bindings) == 1
        session_id = next(iter(gateway._session_bindings))
        assert gateway._session_bindings[session_id] == "qq"
        assert collected[0].payload["content"] == "你好"
        assert collected[0].session_id == session_id

    @pytest.mark.asyncio
    async def test_reuses_group_session_for_same_group(self):
        channel, _, bus, _ = _make_channel(group_policy="open", require_mention=False)
        collected: list[EventEnvelope] = []

        async def collect():
            async for event in bus.subscribe():
                collected.append(event)
                if len(collected) >= 2:
                    break

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.05)

        first = QQInboundMessage(
            text="first",
            chat_type="group",
            chat_id="group-1",
            sender_id="1001",
            sender_name="alice",
            message_id="11",
            target="group:group-1",
            mentioned_bot=True,
        )
        second = QQInboundMessage(
            text="second",
            chat_type="group",
            chat_id="group-1",
            sender_id="1001",
            sender_name="alice",
            message_id="12",
            target="group:group-1",
            mentioned_bot=True,
        )

        await channel.handle_incoming_message(first)
        await channel.handle_incoming_message(second)

        await asyncio.wait_for(task, timeout=2)
        assert collected[0].session_id == collected[1].session_id

    @pytest.mark.asyncio
    async def test_pending_question_routes_to_user_question_answered(self):
        channel, _, bus, _ = _make_channel()
        session_id = "qq_session_1"
        channel._chat_sessions["dm:1001"] = session_id
        channel._pending_questions[session_id] = channel._pending_question_model(
            question_id="q1",
            question="请确认",
        )
        collected: list[EventEnvelope] = []

        async def collect():
            async for event in bus.subscribe():
                collected.append(event)
                if event.type == USER_QUESTION_ANSWERED:
                    break

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.05)

        await channel.handle_incoming_message(
            QQInboundMessage(
                text="确认",
                chat_type="p2p",
                chat_id="1001",
                sender_id="1001",
                sender_name="alice",
                message_id="13",
                target="user:1001",
            )
        )

        await asyncio.wait_for(task, timeout=2)
        assert collected[0].payload["question_id"] == "q1"
        assert collected[0].payload["answer"] == "确认"


class TestOutbound:
    @pytest.mark.asyncio
    async def test_agent_step_completed_sends_reply(self):
        channel, _, _, runtime = _make_channel()
        channel._session_meta["qq_session_1"] = channel._session_meta_model(
            chat_type="p2p",
            chat_id="1001",
            sender_id="1001",
            sender_name="alice",
            target="user:1001",
            reply_to_message_id="10",
            mode="onebot",
        )

        await channel.send_event(
            EventEnvelope(
                type=AGENT_STEP_COMPLETED,
                session_id="qq_session_1",
                turn_id="turn_1",
                source="agent",
                payload={"result": {"content": "你好，我是助手"}},
            )
        )

        assert runtime.sent_messages[-1]["target"] == "user:1001"
        assert runtime.sent_messages[-1]["text"] == "你好，我是助手"

    @pytest.mark.asyncio
    async def test_user_question_asked_tracks_pending_question(self):
        channel, _, _, runtime = _make_channel()
        channel._session_meta["qq_session_1"] = channel._session_meta_model(
            chat_type="p2p",
            chat_id="1001",
            sender_id="1001",
            sender_name="alice",
            target="user:1001",
            reply_to_message_id="10",
            mode="official",
        )

        await channel.send_event(
            EventEnvelope(
                type=USER_QUESTION_ASKED,
                session_id="qq_session_1",
                turn_id="turn_1",
                source="agent",
                payload={"question_id": "q1", "question": "请确认"},
            )
        )

        assert channel._pending_questions["qq_session_1"].question_id == "q1"
        assert runtime.sent_messages[-1]["text"] == "请确认"

    @pytest.mark.asyncio
    async def test_tool_progress_can_be_disabled(self):
        channel, _, _, runtime = _make_channel()
        await channel.send_event(
            EventEnvelope(
                type=TOOL_CALL_STARTED,
                session_id="qq_session_1",
                turn_id="turn_1",
                source="agent",
                payload={"tool_name": "search"},
            )
        )
        assert runtime.sent_messages == []

    @pytest.mark.asyncio
    async def test_error_event_sends_error_message(self):
        channel, _, _, runtime = _make_channel()
        channel._session_meta["qq_session_1"] = channel._session_meta_model(
            chat_type="p2p",
            chat_id="1001",
            sender_id="1001",
            sender_name="alice",
            target="user:1001",
            reply_to_message_id="10",
            mode="onebot",
        )

        await channel.send_event(
            EventEnvelope(
                type=ERROR_RAISED,
                session_id="qq_session_1",
                turn_id="turn_1",
                source="agent",
                payload={"error_message": "boom"},
            )
        )

        assert runtime.sent_messages[-1]["text"] == "错误: boom"
