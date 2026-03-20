"""企业微信 Channel 出站单元测试。"""

from __future__ import annotations

import pytest

from agentos.adapters.plugins.wecom.channel import WecomChannel, WecomSessionMeta
from agentos.adapters.plugins.wecom.config import WecomConfig
from agentos.interfaces.ws.gateway import Gateway
from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import AGENT_STEP_COMPLETED, ERROR_RAISED, TOOL_CALL_STARTED, USER_QUESTION_ASKED
from agentos.kernel.runtime.publisher import EventPublisher


class _SimplePluginApi:
    def __init__(self, gateway: Gateway):
        self._gateway = gateway

    def get_gateway(self) -> Gateway:
        return self._gateway


class _FakeWecomClient:
    def __init__(self):
        self.sent_messages: list[dict] = []

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send_text(self, target: str, text: str) -> dict:
        self.sent_messages.append({"target": target, "text": text})
        return {"success": True, "message_id": f"msg:{target}"}


def _make_channel(show_tool_progress: bool = False):
    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)
    client = _FakeWecomClient()
    config = WecomConfig(
        enabled=True,
        bot_id="bot_001",
        secret="secret_001",
        show_tool_progress=show_tool_progress,
    )
    channel = WecomChannel(
        config=config,
        plugin_api=_SimplePluginApi(gateway=gateway),
        client=client,
    )
    channel._session_meta["session-1"] = WecomSessionMeta(
        chat_id="chat-1",
        chat_type="group",
        sender_id="user-1",
        last_message_id="msg-1",
    )
    return channel, client


@pytest.mark.asyncio
async def test_send_agent_reply():
    channel, client = _make_channel()
    await channel.send_event(
        EventEnvelope(
            type=AGENT_STEP_COMPLETED,
            session_id="session-1",
            payload={"final_response": "已完成"},
        )
    )
    assert client.sent_messages == [{"target": "chat-1", "text": "已完成"}]


@pytest.mark.asyncio
async def test_send_user_question_asked_reply():
    channel, client = _make_channel()
    await channel.send_event(
        EventEnvelope(
            type=USER_QUESTION_ASKED,
            session_id="session-1",
            payload={"question": "请补充更多上下文"},
        )
    )
    assert client.sent_messages == [{"target": "chat-1", "text": "请补充更多上下文"}]


@pytest.mark.asyncio
async def test_send_error_reply():
    channel, client = _make_channel()
    await channel.send_event(
        EventEnvelope(
            type=ERROR_RAISED,
            session_id="session-1",
            payload={"error_message": "失败了"},
        )
    )
    assert "失败了" in client.sent_messages[0]["text"]


@pytest.mark.asyncio
async def test_send_tool_progress_reply():
    channel, client = _make_channel(show_tool_progress=True)
    await channel.send_event(
        EventEnvelope(
            type=TOOL_CALL_STARTED,
            session_id="session-1",
            payload={"tool_name": "search"},
        )
    )
    assert "search" in client.sent_messages[0]["text"]


@pytest.mark.asyncio
async def test_send_outbound_to_user_target():
    channel, client = _make_channel()
    result = await channel.send_outbound(target="user:user-1", text="hello")
    assert result["success"] is True
    assert client.sent_messages == [{"target": "user:user-1", "text": "hello"}]
