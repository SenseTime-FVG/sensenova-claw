"""飞书 Channel (FeishuChannel) 单元测试

mock 所有 lark_oapi SDK 调用，验证：
- Channel 基础属性（channel_id, event_filter）
- 入站消息提取（_extract_text）
- 响应策略判断（_should_respond）
- 入站消息到 EventBus 的转换（_on_message_async）
- 出站事件分发（send_event）
- 消息发送（_send_reply, send_outbound）
- 消息截断逻辑
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import (
    AGENT_STEP_COMPLETED,
    CRON_DELIVERY_REQUESTED,
    ERROR_RAISED,
    TOOL_CALL_STARTED,
)
from agentos.adapters.channels.feishu.config import FeishuConfig
from agentos.adapters.channels.feishu.channel import FeishuChannel, FeishuSessionMeta


# ---- 辅助函数 ----


def _make_channel(
    show_tool_progress: bool = False,
    render_mode: str = "text",
    dm_policy: str = "open",
    group_policy: str = "mention",
    allowlist: list[str] | None = None,
) -> tuple[FeishuChannel, MagicMock]:
    """创建测试用 FeishuChannel，返回 (channel, mock_plugin_api)"""
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
    plugin_api = MagicMock()
    channel = FeishuChannel(config=config, plugin_api=plugin_api)
    return channel, plugin_api


def _make_mock_msg(
    msg_type: str = "text",
    content: str = '{"text": "hello"}',
    chat_type: str = "p2p",
    mentions: list | None = None,
):
    """构造飞书 SDK 消息对象 mock"""
    msg = MagicMock()
    msg.message_type = msg_type
    msg.content = content
    msg.chat_type = chat_type
    msg.mentions = mentions
    return msg


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
        msg = _make_mock_msg(msg_type="text", content='{"text": "hello world"}')
        result = ch._extract_text("text", msg.content, "p2p", msg)
        assert result == "hello world"

    def test_extract_empty_text_returns_none(self):
        """空文本应返回 None"""
        ch, _ = _make_channel()
        msg = _make_mock_msg(msg_type="text", content='{"text": "  "}')
        result = ch._extract_text("text", msg.content, "p2p", msg)
        assert result is None

    def test_extract_text_group_removes_mention(self):
        """群聊中应去除 @bot mention 标记"""
        ch, _ = _make_channel()
        mention = MagicMock()
        mention.key = "@_user_1"
        msg = _make_mock_msg(
            msg_type="text",
            content='{"text": "@_user_1 你好"}',
            chat_type="group",
            mentions=[mention],
        )
        result = ch._extract_text("text", msg.content, "group", msg)
        assert result == "你好"

    def test_extract_image_message(self):
        ch, _ = _make_channel()
        msg = _make_mock_msg(msg_type="image")
        result = ch._extract_text("image", msg.content, "p2p", msg)
        assert "图片" in result

    def test_extract_file_message(self):
        ch, _ = _make_channel()
        msg = _make_mock_msg(msg_type="file", content='{"file_name": "doc.pdf"}')
        result = ch._extract_text("file", msg.content, "p2p", msg)
        assert "doc.pdf" in result

    def test_extract_unsupported_type_returns_none(self):
        ch, _ = _make_channel()
        msg = _make_mock_msg(msg_type="audio")
        result = ch._extract_text("audio", msg.content, "p2p", msg)
        assert result is None


# ---- _should_respond 测试 ----


class TestShouldRespond:
    def test_p2p_open_policy(self):
        """dm_policy=open 时，私聊应全部响应"""
        ch, _ = _make_channel(dm_policy="open")
        msg = _make_mock_msg()
        assert ch._should_respond("p2p", "any_user", msg) is True

    def test_p2p_allowlist_hit(self):
        """dm_policy=allowlist 时，在列表中应响应"""
        ch, _ = _make_channel(dm_policy="allowlist", allowlist=["user_a"])
        msg = _make_mock_msg()
        assert ch._should_respond("p2p", "user_a", msg) is True

    def test_p2p_allowlist_miss(self):
        """dm_policy=allowlist 时，不在列表中不应响应"""
        ch, _ = _make_channel(dm_policy="allowlist", allowlist=["user_a"])
        msg = _make_mock_msg()
        assert ch._should_respond("p2p", "user_b", msg) is False

    def test_group_disabled(self):
        """group_policy=disabled 时不应响应"""
        ch, _ = _make_channel(group_policy="disabled")
        msg = _make_mock_msg()
        assert ch._should_respond("group", "any", msg) is False

    def test_group_mention_with_mentions(self):
        """group_policy=mention 且有 @mention 时应响应"""
        ch, _ = _make_channel(group_policy="mention")
        msg = _make_mock_msg(mentions=[MagicMock()])
        assert ch._should_respond("group", "any", msg) is True

    def test_group_mention_without_mentions(self):
        """group_policy=mention 但无 @mention 时不应响应"""
        ch, _ = _make_channel(group_policy="mention")
        msg = _make_mock_msg(mentions=None)
        assert ch._should_respond("group", "any", msg) is False

    def test_group_open_policy(self):
        """group_policy=open 时应全部响应"""
        ch, _ = _make_channel(group_policy="open")
        msg = _make_mock_msg()
        assert ch._should_respond("group", "any", msg) is True

    def test_unknown_chat_type(self):
        """未知 chat_type 应不响应"""
        ch, _ = _make_channel()
        msg = _make_mock_msg()
        assert ch._should_respond("unknown", "any", msg) is False


# ---- _on_message_async 测试 ----


class TestOnMessageAsync:
    async def test_creates_session_and_publishes(self):
        """入站消息应创建 session 并发布 USER_INPUT 事件"""
        ch, plugin_api = _make_channel()
        mock_gateway = MagicMock()
        mock_gateway.bind_session = MagicMock()
        mock_gateway.publish_from_channel = AsyncMock()
        plugin_api.get_gateway.return_value = mock_gateway

        await ch._on_message_async("hello", "chat_001", "p2p", "msg_001", "sender_001")

        # 应调用 bind_session
        mock_gateway.bind_session.assert_called_once()
        args = mock_gateway.bind_session.call_args[0]
        session_id = args[0]
        assert args[1] == "feishu"
        assert session_id.startswith("feishu_")

        # 应发布事件
        mock_gateway.publish_from_channel.assert_awaited_once()
        event = mock_gateway.publish_from_channel.call_args[0][0]
        assert event.type == "user.input"
        assert event.payload["content"] == "hello"
        assert event.session_id == session_id

    async def test_reuses_session_for_same_dm(self):
        """同一个私聊用户应复用 session"""
        ch, plugin_api = _make_channel()
        mock_gateway = MagicMock()
        mock_gateway.bind_session = MagicMock()
        mock_gateway.publish_from_channel = AsyncMock()
        plugin_api.get_gateway.return_value = mock_gateway

        await ch._on_message_async("msg1", "chat_001", "p2p", "m1", "sender_001")
        await ch._on_message_async("msg2", "chat_002", "p2p", "m2", "sender_001")

        # 两次调用应使用相同的 session_id
        calls = mock_gateway.publish_from_channel.call_args_list
        sid1 = calls[0][0][0].session_id
        sid2 = calls[1][0][0].session_id
        assert sid1 == sid2

    async def test_group_session_key(self):
        """群聊应以 group:<chat_id> 作为 session key"""
        ch, plugin_api = _make_channel()
        mock_gateway = MagicMock()
        mock_gateway.bind_session = MagicMock()
        mock_gateway.publish_from_channel = AsyncMock()
        plugin_api.get_gateway.return_value = mock_gateway

        await ch._on_message_async("msg1", "group_chat_001", "group", "m1", "s1")
        await ch._on_message_async("msg2", "group_chat_001", "group", "m2", "s2")

        calls = mock_gateway.publish_from_channel.call_args_list
        sid1 = calls[0][0][0].session_id
        sid2 = calls[1][0][0].session_id
        assert sid1 == sid2  # 同一群聊复用 session


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
    async def test_agent_step_completed(self):
        """AGENT_STEP_COMPLETED 事件应触发回复"""
        ch, _ = _make_channel()
        ch._send_reply = AsyncMock()

        event = EventEnvelope(
            type=AGENT_STEP_COMPLETED,
            session_id="s1",
            payload={"result": {"content": "done"}},
        )
        await ch.send_event(event)
        ch._send_reply.assert_awaited_once_with("s1", "done")

    async def test_agent_step_completed_final_response(self):
        """AGENT_STEP_COMPLETED 事件的 final_response 回退路径"""
        ch, _ = _make_channel()
        ch._send_reply = AsyncMock()

        event = EventEnvelope(
            type=AGENT_STEP_COMPLETED,
            session_id="s1",
            payload={"final_response": "fallback text"},
        )
        await ch.send_event(event)
        ch._send_reply.assert_awaited_once_with("s1", "fallback text")

    async def test_agent_step_completed_empty_text(self):
        """空回复不应触发发送"""
        ch, _ = _make_channel()
        ch._send_reply = AsyncMock()

        event = EventEnvelope(
            type=AGENT_STEP_COMPLETED,
            session_id="s1",
            payload={"result": {"content": ""}},
        )
        await ch.send_event(event)
        ch._send_reply.assert_not_awaited()

    async def test_error_raised(self):
        """ERROR_RAISED 事件应发送错误消息"""
        ch, _ = _make_channel()
        ch._send_reply = AsyncMock()

        event = EventEnvelope(
            type=ERROR_RAISED,
            session_id="s1",
            payload={"error_message": "boom"},
        )
        await ch.send_event(event)
        ch._send_reply.assert_awaited_once()
        text = ch._send_reply.call_args[0][1]
        assert "boom" in text

    async def test_tool_call_started(self):
        """TOOL_CALL_STARTED 事件应发送工具进度"""
        ch, _ = _make_channel()
        ch._send_reply = AsyncMock()

        event = EventEnvelope(
            type=TOOL_CALL_STARTED,
            session_id="s1",
            payload={"tool_name": "bash_command"},
        )
        await ch.send_event(event)
        ch._send_reply.assert_awaited_once()
        text = ch._send_reply.call_args[0][1]
        assert "bash_command" in text

    async def test_tool_call_started_empty_name(self):
        """工具名为空时不应发送"""
        ch, _ = _make_channel()
        ch._send_reply = AsyncMock()

        event = EventEnvelope(
            type=TOOL_CALL_STARTED,
            session_id="s1",
            payload={"tool_name": ""},
        )
        await ch.send_event(event)
        ch._send_reply.assert_not_awaited()

    async def test_cron_delivery_with_to(self):
        """CRON_DELIVERY_REQUESTED 有 to 时应调用 _deliver_cron_text"""
        ch, _ = _make_channel()
        ch._deliver_cron_text = AsyncMock()

        event = EventEnvelope(
            type=CRON_DELIVERY_REQUESTED,
            session_id="s1",
            payload={"text": "cron msg", "to": "chat_123"},
        )
        await ch.send_event(event)
        ch._deliver_cron_text.assert_awaited_once_with("cron msg", "chat_123")


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
        ch._client = MagicMock()  # 有 client
        # _session_meta 为空，不应抛异常
        await ch._send_reply("unknown_session", "hello")

    @patch("agentos.adapters.channels.feishu.channel.asyncio.to_thread")
    async def test_truncates_long_text(self, mock_to_thread):
        """超过 20000 字符的消息应被截断"""
        ch, _ = _make_channel(render_mode="text")
        mock_response = MagicMock()
        mock_response.success.return_value = True
        ch._client = MagicMock()

        ch._session_meta["s1"] = FeishuSessionMeta(
            chat_id="chat_1", chat_type="p2p",
            last_message_id="m1", sender_id="u1",
        )

        long_text = "A" * 25000
        mock_to_thread.return_value = mock_response
        await ch._send_reply("s1", long_text)
        # 应至少被调用一次（分片后）
        assert mock_to_thread.await_count >= 1

    @patch("agentos.adapters.channels.feishu.channel.asyncio.to_thread")
    async def test_send_reply_api_failure_breaks(self, mock_to_thread):
        """API 返回失败时应中断后续分片发送"""
        ch, _ = _make_channel(render_mode="text")
        mock_response = MagicMock()
        mock_response.success.return_value = False
        mock_response.code = 99999
        mock_response.msg = "rate limited"

        ch._client = MagicMock()
        ch._session_meta["s1"] = FeishuSessionMeta(
            chat_id="chat_1", chat_type="p2p",
            last_message_id="m1", sender_id="u1",
        )

        mock_to_thread.return_value = mock_response
        await ch._send_reply("s1", "hello")
        # 失败后应只调用一次就中断
        assert mock_to_thread.await_count == 1


# ---- _deliver_cron_text 测试 ----


class TestDeliverCronText:
    async def test_with_target(self):
        """指定 to 时应调用 send_outbound"""
        ch, _ = _make_channel()
        ch.send_outbound = AsyncMock(return_value={"success": True})
        await ch._deliver_cron_text("cron msg", to="chat_123")
        ch.send_outbound.assert_awaited_once_with(target="chat_123", text="cron msg")

    async def test_broadcast_to_all_sessions(self):
        """无 to 时应广播到所有已知 sessions"""
        ch, _ = _make_channel()
        ch._session_meta = {
            "s1": FeishuSessionMeta("c1", "p2p", "m1", "u1"),
            "s2": FeishuSessionMeta("c2", "group", "m2", "u2"),
        }
        ch._send_reply = AsyncMock()
        await ch._deliver_cron_text("broadcast msg")
        assert ch._send_reply.await_count == 2

    async def test_no_sessions_logs_warning(self):
        """无活跃 session 时不应抛异常"""
        ch, _ = _make_channel()
        ch._session_meta = {}
        ch._send_reply = AsyncMock()
        await ch._deliver_cron_text("msg")
        ch._send_reply.assert_not_awaited()


# ---- send_outbound 测试 ----


class TestSendOutbound:
    async def test_no_client_returns_error(self):
        """未初始化 client 时应返回 error"""
        ch, _ = _make_channel()
        ch._client = None
        result = await ch.send_outbound("target", "text")
        assert result["success"] is False
        assert "not initialized" in result["error"]

    @patch("agentos.adapters.channels.feishu.channel.asyncio.to_thread")
    async def test_user_target_uses_open_id(self, mock_to_thread):
        """user: 前缀的 target 应使用 open_id 类型"""
        ch, _ = _make_channel(render_mode="text")
        mock_response = MagicMock()
        mock_response.success.return_value = True
        mock_response.data.message_id = "sent_001"
        ch._client = MagicMock()

        mock_to_thread.return_value = mock_response
        result = await ch.send_outbound("user:open_id_123", "hello")
        assert result["success"] is True
        assert result["message_id"] == "sent_001"

    @patch("agentos.adapters.channels.feishu.channel.asyncio.to_thread")
    async def test_chat_id_target(self, mock_to_thread):
        """普通 target 应使用 chat_id 类型"""
        ch, _ = _make_channel(render_mode="text")
        mock_response = MagicMock()
        mock_response.success.return_value = True
        mock_response.data.message_id = "sent_002"
        ch._client = MagicMock()

        mock_to_thread.return_value = mock_response
        result = await ch.send_outbound("chat_id_456", "hello")
        assert result["success"] is True

    @patch("agentos.adapters.channels.feishu.channel.asyncio.to_thread")
    async def test_send_outbound_api_failure(self, mock_to_thread):
        """API 失败时应返回 error 信息"""
        ch, _ = _make_channel(render_mode="text")
        mock_response = MagicMock()
        mock_response.success.return_value = False
        mock_response.code = 40003
        mock_response.msg = "invalid receive_id"
        ch._client = MagicMock()

        mock_to_thread.return_value = mock_response
        result = await ch.send_outbound("bad_target", "hello")
        assert result["success"] is False
        assert result["code"] == 40003
