"""QQ 官方 runtime 单元测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from sensenova_claw.adapters.plugins.qq.config import QQConfig, QQOfficialConfig, QQOneBotConfig
from sensenova_claw.adapters.plugins.qq.runtime_official import QQOfficialRuntime


def _make_config() -> QQConfig:
    return QQConfig(
        enabled=True,
        mode="official",
        dm_policy="open",
        group_policy="open",
        allowlist=[],
        group_allowlist=[],
        require_mention=True,
        show_tool_progress=False,
        reply_to_message=True,
        official=QQOfficialConfig(
            app_id="app-1",
            client_secret="secret-1",
            public_key="pub-1",
            sandbox=False,
            webhook_secret="hook-1",
            intents=["PUBLIC_GUILD_MESSAGES"],
        ),
        onebot=QQOneBotConfig(),
    )


@pytest.mark.asyncio
async def test_parse_direct_message_event():
    dispatched = []
    runtime = QQOfficialRuntime(config=_make_config())

    async def collect(message):
        dispatched.append(message)

    runtime.set_message_handler(collect)
    await runtime.handle_event(
        {
            "op": 0,
            "t": "DIRECT_MESSAGE_CREATE",
            "d": {
                "id": "msg-1",
                "content": "你好",
                "author": {"id": "user-1", "username": "alice"},
                "channel_id": "channel-1",
                "guild_id": None,
            },
        }
    )

    assert dispatched
    assert dispatched[0].chat_type == "p2p"
    assert dispatched[0].chat_id == "channel-1"
    assert dispatched[0].target == "direct:channel-1"


@pytest.mark.asyncio
async def test_parse_group_message_event_detects_mention():
    dispatched = []
    runtime = QQOfficialRuntime(config=_make_config())

    async def collect(message):
        dispatched.append(message)

    runtime.set_message_handler(collect)
    await runtime.handle_event(
        {
            "op": 0,
            "t": "AT_MESSAGE_CREATE",
            "d": {
                "id": "msg-2",
                "content": "<@!app-1> 帮我总结",
                "author": {"id": "user-2", "username": "bob"},
                "channel_id": "channel-2",
                "guild_id": "guild-1",
            },
        }
    )

    assert dispatched
    assert dispatched[0].chat_type == "channel"
    assert dispatched[0].chat_id == "channel-2"
    assert dispatched[0].mentioned_bot is True
    assert dispatched[0].target == "channel:channel-2"


@pytest.mark.asyncio
async def test_send_text_posts_to_direct_message_api():
    runtime = QQOfficialRuntime(config=_make_config())
    runtime._access_token = "token-1"
    runtime._token_expire_at = 9999999999
    response = Mock()
    response.json.return_value = {"id": "msg-100"}
    response.raise_for_status.return_value = None
    client = AsyncMock()
    client.post.return_value = response

    with patch("sensenova_claw.adapters.plugins.qq.runtime_official.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value = client
        result = await runtime.send_text("direct:channel-1", "你好")

    assert result["success"] is True
    assert result["message_id"] == "msg-100"
    client.post.assert_awaited_once()
    assert client.post.await_args.kwargs["headers"]["Authorization"] == "QQBot token-1"
