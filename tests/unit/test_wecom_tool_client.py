"""企业微信 SDK 包装层单元测试。"""

from __future__ import annotations

import pytest

from agentos.adapters.plugins.wecom.config import WecomConfig
from agentos.adapters.plugins.wecom.tool_client import WecomIncomingMessage, WecomToolClient


class _FakeSdkClient:
    def __init__(self, options):
        self.options = options
        self.handlers: dict[str, object] = {}
        self.connect_called = False
        self.disconnect_called = False
        self.sent_messages: list[dict] = []

    def on(self, event_name: str):
        def decorator(handler):
            self.handlers[event_name] = handler
            return handler

        return decorator

    async def connect(self):
        self.connect_called = True
        return self

    def disconnect(self):
        self.disconnect_called = True

    async def send_message(self, chatid: str, body: dict):
        self.sent_messages.append({"chatid": chatid, "body": body})
        return {
            "errcode": 0,
            "errmsg": "ok",
            "headers": {"req_id": "send_001"},
        }


class _FakeOptions:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


@pytest.mark.asyncio
async def test_start_builds_sdk_client_and_registers_text_handler():
    messages: list[WecomIncomingMessage] = []

    def _factory(options):
        return _FakeSdkClient(options)

    client = WecomToolClient(
        config=WecomConfig(
            enabled=True,
            bot_id="bot_001",
            secret="secret_001",
            websocket_url="wss://example.invalid",
        ),
        on_text_message=messages.append,
        client_factory=_factory,
        options_cls=_FakeOptions,
    )

    await client.start()

    assert client._sdk_client is not None
    assert isinstance(client._sdk_client.options, _FakeOptions)
    assert client._sdk_client.options.kwargs["bot_id"] == "bot_001"
    assert client._sdk_client.options.kwargs["secret"] == "secret_001"
    assert client._sdk_client.options.kwargs["ws_url"] == "wss://example.invalid"
    assert "message.text" in client._sdk_client.handlers
    assert client._sdk_client.connect_called is True


@pytest.mark.asyncio
async def test_text_frame_is_converted_to_incoming_message():
    messages: list[WecomIncomingMessage] = []

    client = WecomToolClient(
        config=WecomConfig(enabled=True, bot_id="bot", secret="secret"),
        on_text_message=messages.append,
        client_factory=lambda options: _FakeSdkClient(options),
        options_cls=_FakeOptions,
    )
    await client.start()

    handler = client._sdk_client.handlers["message.text"]
    frame = {
        "headers": {"req_id": "req_001"},
        "body": {
            "msgtype": "text",
            "text": {"content": "你好"},
            "chatid": "chat_001",
            "chattype": "group",
            "from": {"userid": "user_001"},
        },
    }

    await handler(frame)

    assert messages == [
        WecomIncomingMessage(
            text="你好",
            chat_id="chat_001",
            chat_type="group",
            sender_id="user_001",
            message_id="req_001",
        )
    ]


@pytest.mark.asyncio
async def test_single_chat_type_is_normalized_to_p2p():
    messages: list[WecomIncomingMessage] = []

    client = WecomToolClient(
        config=WecomConfig(enabled=True, bot_id="bot", secret="secret"),
        on_text_message=messages.append,
        client_factory=lambda options: _FakeSdkClient(options),
        options_cls=_FakeOptions,
    )
    await client.start()

    handler = client._sdk_client.handlers["message.text"]
    frame = {
        "headers": {"req_id": "req_002"},
        "body": {
            "msgtype": "text",
            "text": {"content": "测试"},
            "chattype": "single",
            "from": {"userid": "user_002"},
        },
    }

    await handler(frame)

    assert messages == [
        WecomIncomingMessage(
            text="测试",
            chat_id="user_002",
            chat_type="p2p",
            sender_id="user_002",
            message_id="req_002",
        )
    ]


@pytest.mark.asyncio
async def test_send_text_uses_markdown_message():
    client = WecomToolClient(
        config=WecomConfig(enabled=True, bot_id="bot", secret="secret"),
        on_text_message=lambda message: None,
        client_factory=lambda options: _FakeSdkClient(options),
        options_cls=_FakeOptions,
    )
    await client.start()

    result = await client.send_text("chat_001", "hello **world**")

    assert result["success"] is True
    assert client._sdk_client.sent_messages == [
        {
            "chatid": "chat_001",
            "body": {
                "msgtype": "markdown",
                "markdown": {"content": "hello **world**"},
            },
        }
    ]


@pytest.mark.asyncio
async def test_stop_disconnects_sdk_client():
    client = WecomToolClient(
        config=WecomConfig(enabled=True, bot_id="bot", secret="secret"),
        on_text_message=lambda message: None,
        client_factory=lambda options: _FakeSdkClient(options),
        options_cls=_FakeOptions,
    )
    await client.start()
    await client.stop()
    assert client._sdk_client.disconnect_called is True
