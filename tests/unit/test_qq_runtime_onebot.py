"""QQ OneBot runtime 单元测试。"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from sensenova_claw.adapters.plugins.qq.config import QQConfig, QQOfficialConfig, QQOneBotConfig
from sensenova_claw.adapters.plugins.qq.runtime_onebot import QQOneBotRuntime, _SSL_CONTEXT


def _make_config() -> QQConfig:
    return QQConfig(
        enabled=True,
        mode="onebot",
        dm_policy="open",
        group_policy="open",
        allowlist=[],
        group_allowlist=[],
        require_mention=True,
        show_tool_progress=False,
        reply_to_message=True,
        official=QQOfficialConfig(),
        onebot=QQOneBotConfig(
            ws_url="ws://127.0.0.1:3001",
            access_token="token-1",
            api_base_url="http://127.0.0.1:3000",
            self_id="424242",
        ),
    )


@pytest.mark.asyncio
async def test_handle_ws_message_dispatches_private_message():
    dispatched = []
    runtime = QQOneBotRuntime(config=_make_config())

    async def collect(message):
        dispatched.append(message)

    runtime.set_message_handler(collect)
    await runtime._handle_ws_payload(
        json.dumps(
            {
                "post_type": "message",
                "message_type": "private",
                "user_id": 1001,
                "message_id": 99,
                "raw_message": "你好",
                "message": [{"type": "text", "data": {"text": "你好"}}],
                "sender": {"nickname": "alice"},
            }
        )
    )

    assert dispatched
    assert dispatched[0].chat_type == "p2p"
    assert dispatched[0].chat_id == "1001"
    assert dispatched[0].target == "user:1001"


@pytest.mark.asyncio
async def test_handle_ws_message_dispatches_group_message_and_detects_mention():
    dispatched = []
    runtime = QQOneBotRuntime(config=_make_config())

    async def collect(message):
        dispatched.append(message)

    runtime.set_message_handler(collect)
    await runtime._handle_ws_payload(
        {
            "post_type": "message",
            "message_type": "group",
            "group_id": 2001,
            "user_id": 1001,
            "message_id": 100,
            "raw_message": "[CQ:at,qq=424242] 帮我查天气",
            "message": [
                {"type": "at", "data": {"qq": "424242"}},
                {"type": "text", "data": {"text": " 帮我查天气"}},
            ],
            "sender": {"nickname": "alice"},
        }
    )

    assert dispatched
    assert dispatched[0].chat_type == "group"
    assert dispatched[0].chat_id == "2001"
    assert dispatched[0].mentioned_bot is True
    assert dispatched[0].target == "group:2001"


@pytest.mark.asyncio
async def test_send_text_calls_group_message_api():
    runtime = QQOneBotRuntime(config=_make_config())
    response = Mock()
    response.json.return_value = {"status": "ok", "data": {"message_id": 123}}
    response.raise_for_status.return_value = None
    client = AsyncMock()
    client.post.return_value = response

    with patch("sensenova_claw.adapters.plugins.qq.runtime_onebot.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value = client
        result = await runtime.send_text("group:2001", "你好")

    assert result["success"] is True
    assert result["message_id"] == "123"
    client.post.assert_awaited_once()
    assert client.post.await_args.kwargs["json"]["group_id"] == 2001
    assert client.post.await_args.kwargs["json"]["message"] == "你好"


@pytest.mark.asyncio
async def test_start_uses_ssl_context_for_websocket():
    runtime = QQOneBotRuntime(config=_make_config())

    fake_ws = AsyncMock()
    with patch("sensenova_claw.adapters.plugins.qq.runtime_onebot.websockets.connect", AsyncMock(return_value=fake_ws)) as connect_mock:
        await runtime.start()

    connect_mock.assert_awaited_once_with(
        "ws://127.0.0.1:3001",
        additional_headers={"Authorization": "Bearer token-1"},
        ssl=_SSL_CONTEXT,
    )
    assert runtime._ws is fake_ws
    await runtime.stop()


@pytest.mark.asyncio
async def test_send_text_uses_ssl_context_for_http_client():
    runtime = QQOneBotRuntime(config=_make_config())
    response = Mock()
    response.json.return_value = {"status": "ok", "data": {"message_id": 123}}
    response.raise_for_status.return_value = None
    client = AsyncMock()
    client.post.return_value = response

    with patch("sensenova_claw.adapters.plugins.qq.runtime_onebot.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value = client
        await runtime.send_text("group:2001", "你好")

    assert client_cls.call_args.kwargs["verify"] is _SSL_CONTEXT
