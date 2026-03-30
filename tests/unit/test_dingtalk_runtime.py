"""DingTalk runtime 单元测试。"""

from __future__ import annotations

import asyncio
import types

import pytest

from sensenova_claw.adapters.plugins.dingtalk.config import DingtalkConfig
from sensenova_claw.adapters.plugins.dingtalk.runtime import DingtalkRuntime


def test_runtime_initial_status_is_idle():
    runtime = DingtalkRuntime(DingtalkConfig(enabled=True, client_id="cid", client_secret="secret"))
    assert runtime._status["status"] == "idle"


@pytest.mark.asyncio
async def test_runtime_start_registers_chatbot_handler_and_launches_task(monkeypatch):
    events: list[str] = []

    class _FakeClient:
        def __init__(self, credential, logger=None):
            self.credential = credential
            self.logger = logger
            self.handlers = {}

        def register_callback_handler(self, topic, handler):
            self.handlers[topic] = handler
            events.append(f"register:{topic}")

        async def start(self):
            for handler in self.handlers.values():
                handler.pre_start()
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

    runtime = DingtalkRuntime(DingtalkConfig(enabled=True, client_id="cid", client_secret="secret"))
    await runtime.start()
    await asyncio.sleep(0)

    assert events == ["register:/v1.0/im/bot/messages/get", "start"]
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
