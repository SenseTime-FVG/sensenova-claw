"""DingTalk Channel 单元测试。"""

from __future__ import annotations

import asyncio

import pytest

from sensenova_claw.adapters.plugins.dingtalk.channel import DingtalkChannel
from sensenova_claw.adapters.plugins.dingtalk.config import DingtalkConfig
from sensenova_claw.adapters.plugins.dingtalk.models import DingtalkInboundMessage
from sensenova_claw.interfaces.ws.gateway import Gateway
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import AGENT_STEP_COMPLETED, TOOL_CALL_STARTED, USER_INPUT, USER_QUESTION_ANSWERED, USER_QUESTION_ASKED
from sensenova_claw.kernel.runtime.publisher import EventPublisher


class _SimplePluginApi:
    def __init__(self, gateway: Gateway):
        self._gateway = gateway

    def get_gateway(self) -> Gateway:
        return self._gateway


class _FakeDingtalkRuntime:
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


class _FailingDingtalkRuntime(_FakeDingtalkRuntime):
    async def start(self) -> None:
        self.started = True
        raise RuntimeError("auth failed")


def _make_channel(
    *,
    dm_policy: str = "open",
    group_policy: str = "open",
    allowlist: list[str] | None = None,
    group_allowlist: list[str] | None = None,
    require_mention: bool = True,
    reply_to_sender: bool = False,
    show_tool_progress: bool = False,
):
    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)
    runtime = _FakeDingtalkRuntime()
    config = DingtalkConfig(
        enabled=True,
        client_id="cid",
        client_secret="secret",
        dm_policy=dm_policy,
        group_policy=group_policy,
        allowlist=allowlist or [],
        group_allowlist=group_allowlist or [],
        require_mention=require_mention,
        reply_to_sender=reply_to_sender,
        show_tool_progress=show_tool_progress,
    )
    channel = DingtalkChannel(
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

    @pytest.mark.asyncio
    async def test_start_failure_marks_channel_failed(self):
        bus = PublicEventBus()
        publisher = EventPublisher(bus=bus)
        gateway = Gateway(publisher=publisher)
        runtime = _FailingDingtalkRuntime()
        channel = DingtalkChannel(
            config=DingtalkConfig(enabled=True, client_id="cid", client_secret="secret"),
            plugin_api=_SimplePluginApi(gateway=gateway),
            runtime=runtime,
        )

        with pytest.raises(RuntimeError, match="auth failed"):
            await channel.start()

        assert channel._sensenova_claw_status == {"status": "failed", "error": "auth failed"}


class TestShouldRespond:
    def test_dm_open_policy(self):
        channel, _, _, _ = _make_channel(dm_policy="open")
        assert channel._should_respond(
            DingtalkInboundMessage(
                text="hello",
                conversation_id="conv-1",
                conversation_type="p2p",
                sender_id="user-1",
                sender_staff_id="staff-1",
                sender_nick="alice",
                message_id="msg-1",
                session_webhook="https://example.com/hook",
                mentioned_bot=False,
            )
        ) is True

    def test_group_require_mention_blocks_message(self):
        channel, _, _, _ = _make_channel(group_policy="open", require_mention=True)
        assert channel._should_respond(
            DingtalkInboundMessage(
                text="hello",
                conversation_id="conv-1",
                conversation_type="group",
                sender_id="user-1",
                sender_staff_id="staff-1",
                sender_nick="alice",
                message_id="msg-1",
                session_webhook="https://example.com/hook",
                mentioned_bot=False,
            )
        ) is False

    def test_group_allowlist_hit(self):
        channel, _, _, _ = _make_channel(group_policy="allowlist", group_allowlist=["staff-1"], require_mention=False)
        assert channel._should_respond(
            DingtalkInboundMessage(
                text="hello",
                conversation_id="conv-1",
                conversation_type="group",
                sender_id="user-1",
                sender_staff_id="staff-1",
                sender_nick="alice",
                message_id="msg-1",
                session_webhook="https://example.com/hook",
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
            DingtalkInboundMessage(
                text="你好",
                conversation_id="conv-1",
                conversation_type="p2p",
                sender_id="user-1",
                sender_staff_id="staff-1",
                sender_nick="alice",
                message_id="msg-1",
                session_webhook="https://example.com/hook",
                conversation_title="Alice",
                mentioned_bot=False,
            )
        )

        await asyncio.wait_for(task, timeout=2)
        assert len(gateway._session_bindings) == 1
        session_id = next(iter(gateway._session_bindings))
        assert gateway._session_bindings[session_id] == "dingtalk"
        assert collected[0].payload["content"] == "你好"
        assert collected[0].session_id == session_id

    @pytest.mark.asyncio
    async def test_reuses_group_session_for_same_conversation(self):
        channel, _, bus, _ = _make_channel(group_policy="open", require_mention=False)
        collected: list[EventEnvelope] = []

        async def collect():
            async for event in bus.subscribe():
                collected.append(event)
                if len(collected) >= 2:
                    break

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.05)

        first = DingtalkInboundMessage(
            text="@机器人 first",
            conversation_id="conv-group-1",
            conversation_type="group",
            sender_id="user-1",
            sender_staff_id="staff-1",
            sender_nick="alice",
            message_id="msg-1",
            session_webhook="https://example.com/hook",
            mentioned_bot=True,
        )
        second = DingtalkInboundMessage(
            text="@机器人 second",
            conversation_id="conv-group-1",
            conversation_type="group",
            sender_id="user-2",
            sender_staff_id="staff-2",
            sender_nick="bob",
            message_id="msg-2",
            session_webhook="https://example.com/hook",
            mentioned_bot=True,
        )

        await channel.handle_incoming_message(first)
        await channel.handle_incoming_message(second)

        await asyncio.wait_for(task, timeout=2)
        assert collected[0].session_id == collected[1].session_id

    @pytest.mark.asyncio
    async def test_answers_pending_question_before_user_input(self):
        channel, _, bus, _ = _make_channel()
        session_id = "dingtalk_ask_001"
        channel._chat_sessions["dm:staff-1"] = session_id
        channel._session_meta[session_id] = channel._session_meta_model(
            conversation_id="conv-1",
            conversation_type="p2p",
            sender_id="user-1",
            sender_staff_id="staff-1",
            sender_nick="alice",
            last_message_id="msg-0",
            session_webhook="https://example.com/hook",
            conversation_title="Alice",
            reply_target="conversation:conv-1",
        )
        channel._pending_questions[session_id] = channel._pending_question_model(
            question_id="question-1",
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
            DingtalkInboundMessage(
                text="确认",
                conversation_id="conv-1",
                conversation_type="p2p",
                sender_id="user-1",
                sender_staff_id="staff-1",
                sender_nick="alice",
                message_id="msg-1",
                session_webhook="https://example.com/hook",
                mentioned_bot=False,
            )
        )

        await asyncio.wait_for(task, timeout=2)
        assert collected[0].payload["question_id"] == "question-1"
        assert collected[0].payload["answer"] == "确认"


class TestOutbound:
    @pytest.mark.asyncio
    async def test_agent_step_completed_replies_to_conversation(self):
        channel, _, _, runtime = _make_channel()
        channel._session_meta["dingtalk_001"] = channel._session_meta_model(
            conversation_id="conv-1",
            conversation_type="group",
            sender_id="user-1",
            sender_staff_id="staff-1",
            sender_nick="alice",
            last_message_id="msg-1",
            session_webhook="https://example.com/hook",
            conversation_title="群聊",
            reply_target="conversation:conv-1",
        )

        await channel.send_event(
            EventEnvelope(
                type=AGENT_STEP_COMPLETED,
                session_id="dingtalk_001",
                source="agent",
                payload={"result": {"content": "处理完成"}},
            )
        )

        assert runtime.sent_messages[-1] == {"target": "webhook:https://example.com/hook", "text": "处理完成"}

    @pytest.mark.asyncio
    async def test_tool_progress_is_sent_when_enabled(self):
        channel, _, _, runtime = _make_channel(show_tool_progress=True)
        channel._session_meta["dingtalk_001"] = channel._session_meta_model(
            conversation_id="conv-1",
            conversation_type="group",
            sender_id="user-1",
            sender_staff_id="staff-1",
            sender_nick="alice",
            last_message_id="msg-1",
            session_webhook="https://example.com/hook",
            conversation_title="群聊",
            reply_target="conversation:conv-1",
        )

        await channel.send_event(
            EventEnvelope(
                type=TOOL_CALL_STARTED,
                session_id="dingtalk_001",
                source="agent",
                payload={"tool_name": "serper_search"},
            )
        )

        assert runtime.sent_messages[-1]["text"] == "正在执行 serper_search..."

    @pytest.mark.asyncio
    async def test_send_outbound_delegates_to_runtime(self):
        channel, _, _, runtime = _make_channel()

        result = await channel.send_outbound(target="user:staff-9", text="主动消息")

        assert result == {"success": True, "message_id": "msg:user:staff-9"}
        assert runtime.sent_messages[-1] == {"target": "user:staff-9", "text": "主动消息"}
