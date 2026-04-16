"""QQ 官方 runtime 单元测试。"""

from __future__ import annotations

import asyncio
import json
import ssl
from unittest.mock import AsyncMock, Mock, patch

import pytest
from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close

from sensenova_claw.adapters.plugins.qq.config import QQConfig, QQOfficialConfig, QQOneBotConfig
from sensenova_claw.adapters.plugins.qq.runtime_official import QQOfficialRuntime, _SSL_CONTEXT


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
            sandbox=False,
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
                "guild_id": "dm-guild-1",
            },
        }
    )

    assert dispatched
    assert dispatched[0].chat_type == "p2p"
    assert dispatched[0].chat_id == "dm-guild-1"
    assert dispatched[0].target == "direct:dm-guild-1"


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
async def test_parse_c2c_message_event():
    dispatched = []
    runtime = QQOfficialRuntime(config=_make_config())

    async def collect(message):
        dispatched.append(message)

    runtime.set_message_handler(collect)
    await runtime.handle_event(
        {
            "op": 0,
            "t": "C2C_MESSAGE_CREATE",
            "d": {
                "id": "msg-3",
                "content": "你好",
                "author": {"user_openid": "openid-3", "username": "carl"},
                "channel_id": "channel-3",
                "guild_id": None,
            },
        }
    )

    assert dispatched
    assert dispatched[0].chat_type == "p2p"
    assert dispatched[0].sender_id == "openid-3"
    assert dispatched[0].chat_id == "openid-3"
    assert dispatched[0].target == "c2c:openid-3"


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
        result = await runtime.send_text("direct:dm-guild-1", "你好")

    assert result["success"] is True
    assert result["message_id"] == "msg-100"
    client.post.assert_awaited_once()
    assert client.post.await_args.args[0] == "/dms/dm-guild-1/messages"
    assert client.post.await_args.kwargs["headers"]["Authorization"] == "QQBot token-1"


@pytest.mark.asyncio
async def test_send_text_posts_to_c2c_message_api():
    runtime = QQOfficialRuntime(config=_make_config())
    runtime._access_token = "token-1"
    runtime._token_expire_at = 9999999999
    response = Mock()
    response.json.return_value = {"id": "msg-101"}
    response.raise_for_status.return_value = None
    client = AsyncMock()
    client.post.return_value = response

    with patch("sensenova_claw.adapters.plugins.qq.runtime_official.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value = client
        result = await runtime.send_text("c2c:openid-3", "你好", reply_to_message_id="msg-3")

    assert result["success"] is True
    assert result["message_id"] == "msg-101"
    assert client.post.await_args.args[0] == "/v2/users/openid-3/messages"
    assert client.post.await_args.kwargs["json"] == {
        "content": "你好",
        "msg_type": 0,
        "msg_seq": 1,
        "msg_id": "msg-3",
    }


@pytest.mark.asyncio
async def test_refresh_access_token_uses_bots_domain():
    runtime = QQOfficialRuntime(config=_make_config())
    response = Mock()
    response.json.return_value = {"access_token": "token-2", "expires_in": 7200}
    response.raise_for_status.return_value = None
    client = AsyncMock()
    client.post.return_value = response

    with patch("sensenova_claw.adapters.plugins.qq.runtime_official.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value = client
        await runtime._refresh_access_token()

    assert runtime._access_token == "token-2"
    client_cls.assert_called_once()
    assert client_cls.call_args.kwargs["base_url"] == "https://bots.qq.com"
    assert client_cls.call_args.kwargs["verify"] is _SSL_CONTEXT
    assert client.post.await_args.args[0] == "/app/getAppAccessToken"
    assert isinstance(_SSL_CONTEXT, ssl.SSLContext)


@pytest.mark.asyncio
async def test_fetch_gateway_uses_gateway_bot_endpoint():
    runtime = QQOfficialRuntime(config=_make_config())
    runtime._access_token = "token-1"
    runtime._token_expire_at = 9999999999
    response = Mock()
    response.json.return_value = {"url": "wss://example.qq/gateway"}
    response.raise_for_status.return_value = None
    client = AsyncMock()
    client.get.return_value = response

    with patch("sensenova_claw.adapters.plugins.qq.runtime_official.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value = client
        gateway = await runtime._fetch_gateway()

    assert gateway == "wss://example.qq/gateway"
    assert client_cls.call_args.kwargs["base_url"] == "https://api.sgroup.qq.com"
    assert client_cls.call_args.kwargs["verify"] is _SSL_CONTEXT
    assert client.get.await_args.args[0] == "/gateway/bot"


@pytest.mark.asyncio
async def test_hello_sends_identify_and_heartbeat():
    runtime = QQOfficialRuntime(config=_make_config())
    runtime._access_token = "token-1"
    runtime._token_expire_at = 9999999999
    sent_payloads = []

    class _FakeWS:
        async def send(self, payload: str) -> None:
            sent_payloads.append(payload)

    runtime._ws = _FakeWS()
    class _FakeTask:
        def cancel(self) -> None:
            return None

    with patch("asyncio.create_task") as create_task:
        def _fake_create_task(coro, name=None):
            coro.close()
            return _FakeTask()

        create_task.side_effect = _fake_create_task
        heartbeat_task = await runtime._handle_gateway_payload({"op": 10, "d": {"heartbeat_interval": 41000}})

    assert heartbeat_task is True
    assert sent_payloads
    identify = json.loads(sent_payloads[0])
    assert identify["op"] == 2
    assert identify["d"]["token"] == "QQBot token-1"
    assert identify["d"]["shard"] == [0, 1]
    assert identify["d"]["intents"] > 0


@pytest.mark.asyncio
async def test_ready_event_updates_session_state():
    runtime = QQOfficialRuntime(config=_make_config())
    handled = await runtime._handle_gateway_payload(
        {
            "op": 0,
            "s": 42,
            "t": "READY",
            "d": {
                "session_id": "sess-1",
                "shard": [0, 1],
                "user": {"id": "bot-1", "username": "qqbot"},
            },
        }
    )

    assert handled is True
    assert runtime._session_id == "sess-1"
    assert runtime._last_seq == 42


@pytest.mark.asyncio
async def test_resumed_event_restores_connected_status_after_reconnect():
    runtime = QQOfficialRuntime(config=_make_config())
    runtime._sensenova_claw_status = {"status": "reconnecting", "error": None}
    runtime._session_id = "sess-1"
    runtime._last_seq = 42

    handled = await runtime._handle_gateway_payload(
        {
            "op": 0,
            "s": 43,
            "t": "RESUMED",
            "d": {},
        }
    )

    assert handled is True
    assert runtime._last_seq == 43
    assert runtime._sensenova_claw_status == {"status": "connected", "error": None}


@pytest.mark.asyncio
async def test_recv_loop_reconnects_and_resumes_after_session_timeout():
    runtime = QQOfficialRuntime(config=_make_config())
    runtime._access_token = "token-1"
    runtime._token_expire_at = 9999999999
    runtime._session_id = "sess-1"
    runtime._last_seq = 42

    sent_payloads = []

    class _ClosedWS:
        def __init__(self) -> None:
            self.recv_calls = 0
            self.closed = False

        async def recv(self) -> str:
            self.recv_calls += 1
            raise ConnectionClosedError(
                Close(4009, "Session timed out"),
                Close(4009, "Session timed out"),
                True,
            )

        async def close(self) -> None:
            self.closed = True

    class _ReplacementWS:
        def __init__(self) -> None:
            self._hello_sent = False

        async def recv(self) -> str:
            if not self._hello_sent:
                self._hello_sent = True
                return json.dumps({"op": 10, "d": {"heartbeat_interval": 41000}})
            raise asyncio.CancelledError

        async def send(self, payload: str) -> None:
            sent_payloads.append(json.loads(payload))

        async def close(self) -> None:
            return None

    runtime._ws = _ClosedWS()

    with patch.object(runtime, "_fetch_gateway", AsyncMock(return_value="wss://example.qq/gateway")), patch(
        "sensenova_claw.adapters.plugins.qq.runtime_official.websockets.connect",
        AsyncMock(return_value=_ReplacementWS()),
    ):
        with pytest.raises(asyncio.CancelledError):
            await runtime._recv_loop()

    assert sent_payloads
    assert sent_payloads[0] == {
        "op": runtime.WS_RESUME,
        "d": {
            "token": "QQBot token-1",
            "session_id": "sess-1",
            "seq": 42,
        },
    }


@pytest.mark.asyncio
async def test_open_gateway_connection_uses_ssl_context():
    runtime = QQOfficialRuntime(config=_make_config())

    with patch.object(runtime, "_fetch_gateway", AsyncMock(return_value="wss://example.qq/gateway")), patch(
        "sensenova_claw.adapters.plugins.qq.runtime_official.websockets.connect",
        AsyncMock(return_value=object()),
    ) as connect_mock:
        await runtime._open_gateway_connection()

    connect_mock.assert_awaited_once_with("wss://example.qq/gateway", ssl=_SSL_CONTEXT)
