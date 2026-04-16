"""DingTalk runtime 单元测试。"""

from __future__ import annotations

import asyncio
import logging
import types
from unittest.mock import AsyncMock, Mock, patch

import pytest

from sensenova_claw.adapters.plugins.dingtalk.config import DingtalkConfig
from sensenova_claw.adapters.plugins.dingtalk.runtime import DingtalkRuntime, _CompatDingTalkStreamClient, _SSL_CONTEXT


def _build_compat_client(*, logger):
    class _FakeBaseClient:
        def __init__(self, credential, logger=None):
            self.credential = credential
            self.logger = logger
            self.websocket = None

        def pre_start(self):
            return None

        async def keepalive(self, websocket):
            del websocket
            return None

        async def background_task(self, json_message):
            del json_message
            return None

    sdk = types.SimpleNamespace(DingTalkStreamClient=_FakeBaseClient)
    credential = types.SimpleNamespace(client_id="cid", client_secret="secret")
    return _CompatDingTalkStreamClient(sdk=sdk, credential=credential, logger_=logger)


def test_runtime_initial_status_is_idle():
    runtime = DingtalkRuntime(DingtalkConfig(enabled=True, client_id="cid", client_secret="secret"))
    assert runtime._status["status"] == "idle"


@pytest.mark.asyncio
async def test_runtime_start_registers_chatbot_handler_and_launches_task(monkeypatch):
    events: list[str] = []

    class _FakeWebSocket:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.sleep(60)
            raise StopAsyncIteration

    class _FakeClient:
        def __init__(self, credential, logger=None):
            self.credential = credential
            self.logger = logger
            self.handlers = {}

        def pre_start(self):
            for handler in self.handlers.values():
                handler.pre_start()

        def register_callback_handler(self, topic, handler):
            self.handlers[topic] = handler
            events.append(f"register:{topic}")

        async def start(self):
            events.append("start")
            await asyncio.sleep(60)

        def get_access_token(self):
            return "token-1"

        def open_connection(self):
            return {"endpoint": "wss://example.com/stream", "ticket": "ticket-1"}

    class _FakeModule:
        Credential = lambda client_id, client_secret: types.SimpleNamespace(
            client_id=client_id,
            client_secret=client_secret,
        )
        DingTalkStreamClient = _FakeClient
        ChatbotMessage = types.SimpleNamespace(TOPIC="/v1.0/im/bot/messages/get")

    monkeypatch.setattr("sensenova_claw.adapters.plugins.dingtalk.runtime.importlib.import_module", lambda _: _FakeModule)
    monkeypatch.setattr(
        "sensenova_claw.adapters.plugins.dingtalk.runtime.websockets.connect",
        lambda uri, *, ssl=None: _FakeWebSocket(),
    )

    runtime = DingtalkRuntime(DingtalkConfig(enabled=True, client_id="cid", client_secret="secret"))
    await runtime.start()
    await asyncio.sleep(0)

    assert events == ["register:/v1.0/im/bot/messages/get"]
    assert runtime._status["status"] == "connected"
    assert runtime._client is not None
    assert runtime._client_task is not None
    assert runtime._client_task.done() is False

    await runtime.stop()


@pytest.mark.asyncio
async def test_send_text_to_user_uses_single_chat_receiver(monkeypatch):
    sent_calls: list[dict] = []

    class _FakeClient:
        def get_access_token(self):
            return "token-1"

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"processQueryKey": "outbound-1"}

    async def _fake_post(self, url, *, headers=None, json=None):
        sent_calls.append({"url": url, "headers": headers, "json": json})
        return _FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient.post", _fake_post)

    runtime = DingtalkRuntime(DingtalkConfig(enabled=True, client_id="cid", client_secret="secret"))
    runtime._client = _FakeClient()

    result = await runtime.send_text("user:staff-1", "你好")

    assert result == {"success": True, "message_id": "outbound-1"}
    assert sent_calls[0]["json"]["msgParam"] == '{"content":"你好"}'
    assert sent_calls[0]["json"]["msgKey"] == "sampleText"
    assert sent_calls[0]["json"]["robotCode"] == "cid"
    assert sent_calls[0]["json"]["userIds"] == "staff-1"


@pytest.mark.asyncio
async def test_send_text_to_conversation_uses_open_conversation_id(monkeypatch):
    sent_calls: list[dict] = []

    class _FakeClient:
        def get_access_token(self):
            return "token-1"

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"processQueryKey": "outbound-2"}

    async def _fake_post(self, url, *, headers=None, json=None):
        sent_calls.append({"url": url, "headers": headers, "json": json})
        return _FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient.post", _fake_post)

    runtime = DingtalkRuntime(DingtalkConfig(enabled=True, client_id="cid", client_secret="secret"))
    runtime._client = _FakeClient()

    result = await runtime.send_text("conversation:cid-123", "群消息")

    assert result == {"success": True, "message_id": "outbound-2"}
    assert sent_calls[0]["json"]["openConversationId"] == "cid-123"
    assert "userIds" not in sent_calls[0]["json"]


@pytest.mark.asyncio
async def test_send_text_to_session_webhook_uses_webhook_endpoint(monkeypatch):
    sent_calls: list[dict] = []

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"errmsg": "ok"}

    async def _fake_post(self, url, *, headers=None, json=None, data=None):
        sent_calls.append({"url": url, "headers": headers, "json": json, "data": data})
        return _FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient.post", _fake_post)

    runtime = DingtalkRuntime(DingtalkConfig(enabled=True, client_id="cid", client_secret="secret"))

    result = await runtime.send_text("webhook:https://example.com/session-webhook", "会话回复")

    assert result == {"success": True, "message_id": ""}
    assert sent_calls[0]["url"] == "https://example.com/session-webhook"
    assert sent_calls[0]["data"] == '{"msgtype":"text","text":{"content":"会话回复"}}'
    assert sent_calls[0]["json"] is None


@pytest.mark.asyncio
async def test_send_text_to_user_uses_ssl_context_for_http_client():
    runtime = DingtalkRuntime(DingtalkConfig(enabled=True, client_id="cid", client_secret="secret"))
    runtime._client = type("_FakeClient", (), {"get_access_token": lambda self: "token-1"})()
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"processQueryKey": "outbound-1"}
    client = AsyncMock()
    client.post.return_value = response

    with patch("sensenova_claw.adapters.plugins.dingtalk.runtime.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value = client
        await runtime.send_text("user:staff-1", "你好")

    assert client_cls.call_args.kwargs["verify"] is _SSL_CONTEXT


@pytest.mark.asyncio
async def test_send_text_to_webhook_uses_ssl_context_for_http_client():
    runtime = DingtalkRuntime(DingtalkConfig(enabled=True, client_id="cid", client_secret="secret"))
    response = Mock()
    response.raise_for_status.return_value = None
    client = AsyncMock()
    client.post.return_value = response

    with patch("sensenova_claw.adapters.plugins.dingtalk.runtime.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value = client
        await runtime.send_text("webhook:https://example.com/session-webhook", "会话回复")

    assert client_cls.call_args.kwargs["verify"] is _SSL_CONTEXT


@pytest.mark.asyncio
async def test_compat_client_uses_ssl_context_for_websocket(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeWebSocket:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise KeyboardInterrupt()

    def _fake_connect(uri, *, ssl=None):
        captured["uri"] = uri
        captured["ssl"] = ssl
        return _FakeWebSocket()

    monkeypatch.setattr("sensenova_claw.adapters.plugins.dingtalk.runtime.websockets.connect", _fake_connect)

    client = _build_compat_client(logger=logging.getLogger("test"))
    client.open_connection = lambda: {"endpoint": "wss://example.com/stream", "ticket": "ticket-1"}

    await client.start()

    assert captured["uri"] == "wss://example.com/stream?ticket=ticket-1"
    assert captured["ssl"] is not None


@pytest.mark.asyncio
async def test_compat_client_logs_unexpected_exception_without_format_error(monkeypatch):
    records: list[tuple[str, object]] = []

    class _FakeLogger:
        def error(self, msg, *args):
            records.append(("error", msg % args if args else msg))

        def info(self, msg, *args):
            records.append(("info", msg % args if args else msg))

        def exception(self, msg, *args):
            records.append(("exception", msg % args if args else msg))
            raise asyncio.CancelledError()

    def _fake_connect(uri, *, ssl=None):
        del uri, ssl
        raise RuntimeError("boom")

    async def _fake_sleep(_seconds):
        return None

    monkeypatch.setattr("sensenova_claw.adapters.plugins.dingtalk.runtime.websockets.connect", _fake_connect)
    monkeypatch.setattr("sensenova_claw.adapters.plugins.dingtalk.runtime.asyncio.sleep", _fake_sleep)

    client = _build_compat_client(logger=_FakeLogger())
    client.open_connection = lambda: {"endpoint": "wss://example.com/stream", "ticket": "ticket-1"}

    with pytest.raises(asyncio.CancelledError):
        await client.start()

    assert ("exception", "unknown exception: boom") in records
