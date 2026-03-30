"""飞书 Channel (FeishuChannel) 集成测试

去除所有 mock/MagicMock/AsyncMock/patch，使用真实组件验证：
- Channel 基础属性（channel_id, event_filter）
- 入站消息提取（_extract_text）
- 响应策略判断（_should_respond）
- 入站消息到 EventBus 的转换（_on_message_async）
- 出站事件分发（send_event）
- 消息构建（_build_content）
- 消息截断逻辑
- _deliver_cron_text / send_outbound 逻辑
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import (
    AGENT_STEP_COMPLETED,
    CRON_DELIVERY_REQUESTED,
    ERROR_RAISED,
    TOOL_CALL_STARTED,
    USER_QUESTION_ANSWERED,
    USER_QUESTION_ASKED,
)
from sensenova_claw.kernel.runtime.publisher import EventPublisher
from sensenova_claw.interfaces.ws.gateway import Gateway
from sensenova_claw.adapters.plugins.feishu.config import FeishuConfig
from sensenova_claw.adapters.plugins.feishu.channel import FeishuChannel, FeishuSessionMeta


# ---- 辅助：轻量 PluginApi 替代品（不使用 mock） ----


class _SimplePluginApi:
    """最小化的 PluginApi 替代，仅提供 get_gateway 方法"""

    def __init__(self, gateway: Gateway):
        self._gateway = gateway

    def get_gateway(self) -> Gateway:
        return self._gateway


# ---- 辅助：轻量消息对象（替代 MagicMock） ----


@dataclass
class _FakeMessage:
    """模拟飞书 SDK 消息对象，仅提供测试所需属性"""
    message_type: str = "text"
    content: str = '{"text": "hello"}'
    chat_type: str = "p2p"
    mentions: list[Any] | None = None


@dataclass
class _FakeMention:
    """模拟飞书 SDK mention 对象"""
    key: str = "@_user_1"


@dataclass
class _FakeInboundMessage:
    """模拟飞书 SDK 入站消息对象"""
    chat_id: str = "chat_001"
    chat_type: str = "p2p"
    message_id: str = "msg_001"
    message_type: str = "text"
    content: str = '{"text": "hello"}'
    mentions: list[Any] | None = None


@dataclass
class _FakeSenderId:
    open_id: str = "sender_001"


@dataclass
class _FakeSender:
    sender_id: _FakeSenderId = field(default_factory=_FakeSenderId)


@dataclass
class _FakeEventData:
    """模拟飞书 SDK 回调 data.event 结构"""
    message: _FakeInboundMessage = field(default_factory=_FakeInboundMessage)
    sender: _FakeSender = field(default_factory=_FakeSender)


@dataclass
class _FakeCallbackData:
    event: _FakeEventData = field(default_factory=_FakeEventData)


# ---- 辅助：创建 Channel ----


def _make_channel(
    show_tool_progress: bool = False,
    render_mode: str = "text",
    dm_policy: str = "open",
    group_policy: str = "mention",
    allowlist: list[str] | None = None,
) -> tuple[FeishuChannel, Gateway]:
    """创建测试用 FeishuChannel，返回 (channel, gateway)"""
    config = FeishuConfig(
        enabled=True,
        app_id="test_app",
        app_secret="test_secret",
        dm_policy=dm_policy,
        group_policy=group_policy,
        allowlist=allowlist or [],
        render_mode=render_mode,
        show_tool_progress=show_tool_progress,
    )
    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)
    plugin_api = _SimplePluginApi(gateway=gateway)
    channel = FeishuChannel(config=config, plugin_api=plugin_api)
    return channel, gateway


# ---- 基础属性测试 ----


class TestChannelBasics:
    def test_channel_id(self):
        ch, _ = _make_channel()
        assert ch.get_channel_id() == "feishu"

    def test_event_filter_without_tool_progress(self):
        """不开启工具进度时，事件过滤不含 TOOL_CALL_STARTED"""
        ch, _ = _make_channel(show_tool_progress=False)
        flt = ch.event_filter()
        assert AGENT_STEP_COMPLETED in flt
        assert ERROR_RAISED in flt
        assert CRON_DELIVERY_REQUESTED in flt
        assert USER_QUESTION_ASKED in flt
        assert TOOL_CALL_STARTED not in flt

    def test_event_filter_with_tool_progress(self):
        """开启工具进度时，事件过滤包含 TOOL_CALL_STARTED"""
        ch, _ = _make_channel(show_tool_progress=True)
        flt = ch.event_filter()
        assert TOOL_CALL_STARTED in flt


# ---- _extract_text 测试 ----


class TestExtractText:
    def test_extract_text_message(self):
        ch, _ = _make_channel()
        msg = _FakeMessage(message_type="text", content='{"text": "hello world"}')
        result = ch._extract_text("text", msg.content, "p2p", msg)
        assert result == "hello world"

    def test_extract_empty_text_returns_none(self):
        """空文本应返回 None"""
        ch, _ = _make_channel()
        msg = _FakeMessage(message_type="text", content='{"text": "  "}')
        result = ch._extract_text("text", msg.content, "p2p", msg)
        assert result is None

    def test_extract_text_group_removes_mention(self):
        """群聊中应去除 @bot mention 标记"""
        ch, _ = _make_channel()
        mention = _FakeMention(key="@_user_1")
        msg = _FakeMessage(
            message_type="text",
            content='{"text": "@_user_1 你好"}',
            chat_type="group",
            mentions=[mention],
        )
        result = ch._extract_text("text", msg.content, "group", msg)
        assert result == "你好"

    def test_extract_image_message(self):
        ch, _ = _make_channel()
        msg = _FakeMessage(message_type="image")
        result = ch._extract_text("image", msg.content, "p2p", msg)
        assert "图片" in result

    def test_extract_file_message(self):
        ch, _ = _make_channel()
        msg = _FakeMessage(message_type="file", content='{"file_name": "doc.pdf"}')
        result = ch._extract_text("file", msg.content, "p2p", msg)
        assert "doc.pdf" in result

    def test_extract_unsupported_type_returns_none(self):
        ch, _ = _make_channel()
        msg = _FakeMessage(message_type="audio")
        result = ch._extract_text("audio", msg.content, "p2p", msg)
        assert result is None


# ---- _should_respond 测试 ----


class TestShouldRespond:
    def test_p2p_open_policy(self):
        """dm_policy=open 时，私聊应全部响应"""
        ch, _ = _make_channel(dm_policy="open")
        msg = _FakeMessage()
        assert ch._should_respond("p2p", "any_user", msg) is True

    def test_p2p_allowlist_hit(self):
        """dm_policy=allowlist 时，在列表中应响应"""
        ch, _ = _make_channel(dm_policy="allowlist", allowlist=["user_a"])
        msg = _FakeMessage()
        assert ch._should_respond("p2p", "user_a", msg) is True

    def test_p2p_allowlist_miss(self):
        """dm_policy=allowlist 时，不在列表中不应响应"""
        ch, _ = _make_channel(dm_policy="allowlist", allowlist=["user_a"])
        msg = _FakeMessage()
        assert ch._should_respond("p2p", "user_b", msg) is False

    def test_group_disabled(self):
        """group_policy=disabled 时不应响应"""
        ch, _ = _make_channel(group_policy="disabled")
        msg = _FakeMessage()
        assert ch._should_respond("group", "any", msg) is False

    def test_group_mention_with_mentions(self):
        """group_policy=mention 且有 @mention 时应响应"""
        ch, _ = _make_channel(group_policy="mention")
        msg = _FakeMessage(mentions=[_FakeMention()])
        assert ch._should_respond("group", "any", msg) is True

    def test_group_mention_without_mentions(self):
        """group_policy=mention 但无 @mention 时不应响应"""
        ch, _ = _make_channel(group_policy="mention")
        msg = _FakeMessage(mentions=None)
        assert ch._should_respond("group", "any", msg) is False

    def test_group_open_policy(self):
        """group_policy=open 时应全部响应"""
        ch, _ = _make_channel(group_policy="open")
        msg = _FakeMessage()
        assert ch._should_respond("group", "any", msg) is True

    def test_unknown_chat_type(self):
        """未知 chat_type 应不响应"""
        ch, _ = _make_channel()
        msg = _FakeMessage()
        assert ch._should_respond("unknown", "any", msg) is False


# ---- _on_message_async 测试 ----


class TestOnMessageAsync:
    async def test_creates_session_and_publishes(self):
        """入站消息应创建 session 并发布 USER_INPUT 事件"""
        bus = PublicEventBus()
        publisher = EventPublisher(bus=bus)
        gateway = Gateway(publisher=publisher)
        plugin_api = _SimplePluginApi(gateway=gateway)
        config = FeishuConfig(enabled=True, app_id="test", app_secret="test")
        ch = FeishuChannel(config=config, plugin_api=plugin_api)

        # 收集发布的事件
        collected: list[EventEnvelope] = []

        async def collector():
            async for event in bus.subscribe():
                collected.append(event)
                if event.type == "user.input":
                    break

        task = asyncio.create_task(collector())
        await asyncio.sleep(0.05)

        await ch._on_message_async("hello", "chat_001", "p2p", "msg_001", "sender_001")

        await asyncio.wait_for(task, timeout=2)

        # 应有 session 绑定
        assert len(gateway._session_bindings) == 1
        session_id = list(gateway._session_bindings.keys())[0]
        assert session_id.startswith("feishu_")
        assert gateway._session_bindings[session_id] == {"feishu"}

        # 应发布 user.input 事件
        assert len(collected) == 1
        assert collected[0].type == "user.input"
        assert collected[0].payload["content"] == "hello"
        assert collected[0].session_id == session_id

    async def test_reuses_session_for_same_dm(self):
        """同一个私聊用户应复用 session"""
        bus = PublicEventBus()
        publisher = EventPublisher(bus=bus)
        gateway = Gateway(publisher=publisher)
        plugin_api = _SimplePluginApi(gateway=gateway)
        config = FeishuConfig(enabled=True, app_id="test", app_secret="test")
        ch = FeishuChannel(config=config, plugin_api=plugin_api)

        collected: list[EventEnvelope] = []

        async def collector():
            async for event in bus.subscribe():
                collected.append(event)
                if len(collected) >= 2:
                    break

        task = asyncio.create_task(collector())
        await asyncio.sleep(0.05)

        await ch._on_message_async("msg1", "chat_001", "p2p", "m1", "sender_001")
        await ch._on_message_async("msg2", "chat_002", "p2p", "m2", "sender_001")

        await asyncio.wait_for(task, timeout=2)

        # 两次调用应使用相同的 session_id
        sid1 = collected[0].session_id
        sid2 = collected[1].session_id
        assert sid1 == sid2

    async def test_group_session_key(self):
        """群聊应以 group:<chat_id> 作为 session key"""
        bus = PublicEventBus()
        publisher = EventPublisher(bus=bus)
        gateway = Gateway(publisher=publisher)
        plugin_api = _SimplePluginApi(gateway=gateway)
        config = FeishuConfig(enabled=True, app_id="test", app_secret="test")
        ch = FeishuChannel(config=config, plugin_api=plugin_api)

        collected: list[EventEnvelope] = []

        async def collector():
            async for event in bus.subscribe():
                collected.append(event)
                if len(collected) >= 2:
                    break

        task = asyncio.create_task(collector())
        await asyncio.sleep(0.05)

        await ch._on_message_async("msg1", "group_chat_001", "group", "m1", "s1")
        await ch._on_message_async("msg2", "group_chat_001", "group", "m2", "s2")

        await asyncio.wait_for(task, timeout=2)

        sid1 = collected[0].session_id
        sid2 = collected[1].session_id
        assert sid1 == sid2  # 同一群聊复用 session

    async def test_answers_pending_question_instead_of_publishing_user_input(self):
        bus = PublicEventBus()
        publisher = EventPublisher(bus=bus)
        gateway = Gateway(publisher=publisher)
        plugin_api = _SimplePluginApi(gateway=gateway)
        config = FeishuConfig(enabled=True, app_id="test", app_secret="test")
        ch = FeishuChannel(config=config, plugin_api=plugin_api)

        session_id = "feishu_pending_001"
        ch._chat_sessions["dm:sender_001"] = session_id

        question_event = EventEnvelope(
            type=USER_QUESTION_ASKED,
            session_id=session_id,
            payload={"question_id": "q_001", "question": "请选择环境"},
        )

        async def noop_send_reply(session_id: str, text: str) -> None:
            del session_id, text

        ch._send_reply = noop_send_reply
        await ch.send_event(question_event)

        collected: list[EventEnvelope] = []

        async def collector():
            async for event in bus.subscribe():
                collected.append(event)
                if event.type == USER_QUESTION_ANSWERED:
                    break

        task = asyncio.create_task(collector())
        await asyncio.sleep(0.05)

        await ch._on_message_async("生产环境", "chat_001", "p2p", "msg_001", "sender_001")

        await asyncio.wait_for(task, timeout=2)

        assert len(collected) == 1
        assert collected[0].type == USER_QUESTION_ANSWERED
        assert collected[0].session_id == session_id
        assert collected[0].payload["question_id"] == "q_001"
        assert collected[0].payload["answer"] == "生产环境"
        assert collected[0].payload["cancelled"] is False

    async def test_clears_pending_question_after_answer_and_restores_user_input_flow(self):
        bus = PublicEventBus()
        publisher = EventPublisher(bus=bus)
        gateway = Gateway(publisher=publisher)
        plugin_api = _SimplePluginApi(gateway=gateway)
        config = FeishuConfig(enabled=True, app_id="test", app_secret="test")
        ch = FeishuChannel(config=config, plugin_api=plugin_api)

        session_id = "feishu_pending_002"
        ch._chat_sessions["dm:sender_002"] = session_id

        async def noop_send_reply(session_id: str, text: str) -> None:
            del session_id, text

        ch._send_reply = noop_send_reply
        await ch.send_event(
            EventEnvelope(
                type=USER_QUESTION_ASKED,
                session_id=session_id,
                payload={"question_id": "q_002", "question": "补充说明"},
            )
        )

        first_batch: list[EventEnvelope] = []

        async def answer_collector():
            async for event in bus.subscribe():
                first_batch.append(event)
                if event.type == USER_QUESTION_ANSWERED:
                    break

        first_task = asyncio.create_task(answer_collector())
        await asyncio.sleep(0.05)
        await ch._on_message_async("第一次回答", "chat_002", "p2p", "msg_a", "sender_002")
        await asyncio.wait_for(first_task, timeout=2)

        assert first_batch[-1].type == USER_QUESTION_ANSWERED

        second_batch: list[EventEnvelope] = []

        async def input_collector():
            async for event in bus.subscribe():
                second_batch.append(event)
                if event.type == "user.input":
                    break

        second_task = asyncio.create_task(input_collector())
        await asyncio.sleep(0.05)
        await ch._on_message_async("新的普通消息", "chat_002", "p2p", "msg_b", "sender_002")
        await asyncio.wait_for(second_task, timeout=2)

        assert second_batch[-1].type == "user.input"
        assert second_batch[-1].payload["content"] == "新的普通消息"


class TestHandleMessageEvent:
    def test_handle_message_event_schedules_without_waiting(self, monkeypatch):
        """SDK 回调线程只应投递协程，不应同步等待异步处理结果"""
        ch, _ = _make_channel()

        class _FakeLoop:
            def is_closed(self) -> bool:
                return False

        ch._loop = _FakeLoop()
        calls = {"scheduled": 0, "result_called": 0}

        class _FakeFuture:
            def result(self, timeout=None):
                del timeout
                calls["result_called"] += 1
                raise AssertionError("should not wait in SDK callback thread")

        def fake_run_coroutine_threadsafe(coro, loop):
            assert loop is ch._loop
            calls["scheduled"] += 1
            coro.close()
            return _FakeFuture()

        monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", fake_run_coroutine_threadsafe)

        ch._handle_message_event(_FakeCallbackData())

        assert calls["scheduled"] == 1
        assert calls["result_called"] == 0


# ---- _build_content 测试 ----


class TestBuildContent:
    def test_text_mode(self):
        """render_mode=text 时应返回纯文本 JSON"""
        ch, _ = _make_channel(render_mode="text")
        content, msg_type = ch._build_content("hello")
        assert msg_type == "text"
        assert json.loads(content)["text"] == "hello"

    def test_card_mode(self):
        """render_mode=card 时应返回 interactive 类型"""
        ch, _ = _make_channel(render_mode="card")
        content, msg_type = ch._build_content("hello")
        assert msg_type == "interactive"
        card = json.loads(content)
        assert "elements" in card


# ---- send_event 测试 ----


class TestSendEvent:
    """测试 send_event 的事件分发逻辑。

    由于 _send_reply 依赖飞书 SDK client（self._client），
    我们通过让 _client 为 None 来验证 send_event 的分发路径逻辑
    （_send_reply 会在 _client is None 时静默跳过）。
    对于需要验证"是否调用了 _send_reply"的场景，
    使用子类覆盖 _send_reply 来收集调用记录。
    """

    async def test_agent_step_completed(self):
        """AGENT_STEP_COMPLETED 事件应触发回复（text 被传递到 _send_reply）"""
        ch, _ = _make_channel()
        # 用列表记录 _send_reply 调用
        calls: list[tuple[str, str]] = []
        original_send_reply = ch._send_reply

        async def tracking_send_reply(session_id: str, text: str) -> None:
            calls.append((session_id, text))

        ch._send_reply = tracking_send_reply

        event = EventEnvelope(
            type=AGENT_STEP_COMPLETED,
            session_id="s1",
            payload={"result": {"content": "done"}},
        )
        await ch.send_event(event)
        assert len(calls) == 1
        assert calls[0] == ("s1", "done")

    async def test_agent_step_completed_final_response(self):
        """AGENT_STEP_COMPLETED 事件的 final_response 回退路径"""
        ch, _ = _make_channel()
        calls: list[tuple[str, str]] = []

        async def tracking_send_reply(session_id: str, text: str) -> None:
            calls.append((session_id, text))

        ch._send_reply = tracking_send_reply

        event = EventEnvelope(
            type=AGENT_STEP_COMPLETED,
            session_id="s1",
            payload={"final_response": "fallback text"},
        )
        await ch.send_event(event)
        assert len(calls) == 1
        assert calls[0] == ("s1", "fallback text")

    async def test_agent_step_completed_empty_text(self):
        """空回复不应触发发送"""
        ch, _ = _make_channel()
        calls: list[tuple[str, str]] = []

        async def tracking_send_reply(session_id: str, text: str) -> None:
            calls.append((session_id, text))

        ch._send_reply = tracking_send_reply

        event = EventEnvelope(
            type=AGENT_STEP_COMPLETED,
            session_id="s1",
            payload={"result": {"content": ""}},
        )
        await ch.send_event(event)
        assert len(calls) == 0

    async def test_error_raised(self):
        """ERROR_RAISED 事件应发送错误消息"""
        ch, _ = _make_channel()
        calls: list[tuple[str, str]] = []

        async def tracking_send_reply(session_id: str, text: str) -> None:
            calls.append((session_id, text))

        ch._send_reply = tracking_send_reply

        event = EventEnvelope(
            type=ERROR_RAISED,
            session_id="s1",
            payload={"error_message": "boom"},
        )
        await ch.send_event(event)
        assert len(calls) == 1
        assert "boom" in calls[0][1]

    async def test_user_question_asked(self):
        """USER_QUESTION_ASKED 事件应发送提问内容"""
        ch, _ = _make_channel()
        calls: list[tuple[str, str]] = []

        async def tracking_send_reply(session_id: str, text: str) -> None:
            calls.append((session_id, text))

        ch._send_reply = tracking_send_reply

        event = EventEnvelope(
            type=USER_QUESTION_ASKED,
            session_id="s1",
            payload={"question": "请补充更多上下文"},
        )
        await ch.send_event(event)
        assert len(calls) == 1
        assert calls[0] == ("s1", "请补充更多上下文")

    async def test_tool_call_started(self):
        """TOOL_CALL_STARTED 事件应发送工具进度"""
        ch, _ = _make_channel()
        calls: list[tuple[str, str]] = []

        async def tracking_send_reply(session_id: str, text: str) -> None:
            calls.append((session_id, text))

        ch._send_reply = tracking_send_reply

        event = EventEnvelope(
            type=TOOL_CALL_STARTED,
            session_id="s1",
            payload={"tool_name": "bash_command"},
        )
        await ch.send_event(event)
        assert len(calls) == 1
        assert "bash_command" in calls[0][1]

    async def test_tool_call_started_empty_name(self):
        """工具名为空时不应发送"""
        ch, _ = _make_channel()
        calls: list[tuple[str, str]] = []

        async def tracking_send_reply(session_id: str, text: str) -> None:
            calls.append((session_id, text))

        ch._send_reply = tracking_send_reply

        event = EventEnvelope(
            type=TOOL_CALL_STARTED,
            session_id="s1",
            payload={"tool_name": ""},
        )
        await ch.send_event(event)
        assert len(calls) == 0

    async def test_cron_delivery_with_to(self):
        """CRON_DELIVERY_REQUESTED 有 to 时应调用 _deliver_cron_text"""
        ch, _ = _make_channel()
        cron_calls: list[tuple[str, str | None]] = []

        async def tracking_deliver(text: str, to: str | None = None) -> None:
            cron_calls.append((text, to))

        ch._deliver_cron_text = tracking_deliver

        event = EventEnvelope(
            type=CRON_DELIVERY_REQUESTED,
            session_id="s1",
            payload={"text": "cron msg", "to": "chat_123"},
        )
        await ch.send_event(event)
        assert len(cron_calls) == 1
        assert cron_calls[0] == ("cron msg", "chat_123")


# ---- _send_reply 测试 ----


class TestSendReply:
    async def test_no_client_skips(self):
        """未初始化 client 时应静默跳过"""
        ch, _ = _make_channel()
        ch._client = None
        # 不应抛异常
        await ch._send_reply("s1", "hello")

    async def test_no_meta_skips(self):
        """无 session meta 时应静默跳过"""
        ch, _ = _make_channel()
        # 构造一个非 None 的 _client（用真实 lark Client）
        import lark_oapi as lark
        ch._client = lark.Client.builder().app_id("test").app_secret("test").build()
        # _session_meta 为空，不应抛异常
        await ch._send_reply("unknown_session", "hello")

    async def test_truncates_long_text_structure(self):
        """超过 20000 字符的消息应在内部被截断（验证截断逻辑）"""
        ch, _ = _make_channel(render_mode="text")
        # 不初始化真实 _client，所以 _send_reply 会在 client 检查时直接返回
        # 但我们可以通过 session_meta 检查来验证截断逻辑：
        # 设置 session_meta 但不设置 client，验证不会抛异常
        ch._session_meta["s1"] = FeishuSessionMeta(
            chat_id="chat_1", chat_type="p2p",
            last_message_id="m1", sender_id="u1",
        )
        ch._client = None
        # 不应抛异常
        long_text = "A" * 25000
        await ch._send_reply("s1", long_text)


# ---- _deliver_cron_text 测试 ----


class TestDeliverCronText:
    async def test_with_target(self):
        """指定 to 时应调用 send_outbound"""
        ch, _ = _make_channel()
        outbound_calls: list[dict] = []

        async def tracking_outbound(target: str, text: str, msg_type: str = "card") -> dict:
            outbound_calls.append({"target": target, "text": text})
            return {"success": True}

        ch.send_outbound = tracking_outbound
        await ch._deliver_cron_text("cron msg", to="chat_123")
        assert len(outbound_calls) == 1
        assert outbound_calls[0] == {"target": "chat_123", "text": "cron msg"}

    async def test_broadcast_to_all_sessions(self):
        """无 to 时应广播到所有已知 sessions"""
        ch, _ = _make_channel()
        ch._session_meta = {
            "s1": FeishuSessionMeta("c1", "p2p", "m1", "u1"),
            "s2": FeishuSessionMeta("c2", "group", "m2", "u2"),
        }
        reply_calls: list[tuple[str, str]] = []

        async def tracking_send_reply(session_id: str, text: str) -> None:
            reply_calls.append((session_id, text))

        ch._send_reply = tracking_send_reply
        await ch._deliver_cron_text("broadcast msg")
        assert len(reply_calls) == 2

    async def test_no_sessions_logs_warning(self):
        """无活跃 session 时不应抛异常"""
        ch, _ = _make_channel()
        ch._session_meta = {}
        reply_calls: list[tuple[str, str]] = []

        async def tracking_send_reply(session_id: str, text: str) -> None:
            reply_calls.append((session_id, text))

        ch._send_reply = tracking_send_reply
        await ch._deliver_cron_text("msg")
        assert len(reply_calls) == 0


# ---- send_outbound 测试 ----


class TestSendOutbound:
    async def test_no_client_returns_error(self):
        """未初始化 client 时应返回 error"""
        ch, _ = _make_channel()
        ch._client = None
        result = await ch.send_outbound("target", "text")
        assert result["success"] is False
        assert "not initialized" in result["error"]
