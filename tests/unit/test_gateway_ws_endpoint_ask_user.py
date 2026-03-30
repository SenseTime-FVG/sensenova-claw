"""WebSocket endpoint 的 ask_user 相关单测（无真实端口依赖）。"""

from __future__ import annotations

import types
from dataclasses import dataclass

import pytest
from fastapi import WebSocketDisconnect

from sensenova_claw.app.gateway import main as gateway_main
from sensenova_claw.adapters.channels.websocket_channel import WebSocketChannel
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import (
    PROACTIVE_RESULT,
    TOOL_CONFIRMATION_REQUESTED,
    TOOL_CONFIRMATION_RESOLVED,
    USER_INPUT,
    USER_QUESTION_ANSWERED,
    USER_QUESTION_ASKED,
)


class _FakeGateway:
    def __init__(self):
        self.bind_calls: list[tuple[str, str]] = []
        self.published: list[EventEnvelope] = []
        self.create_session_calls: list[dict[str, object]] = []
        self.agent_registry = types.SimpleNamespace(get=lambda _aid: None)

    def bind_session(self, session_id: str, channel_id: str) -> None:
        self.bind_calls.append((session_id, channel_id))

    async def create_session(
        self,
        agent_id: str = "default",
        meta: dict | None = None,
        channel_id: str = "",
    ) -> dict:
        self.create_session_calls.append({
            "agent_id": agent_id,
            "meta": meta or {},
            "channel_id": channel_id,
        })
        return {
            "session_id": f"sess_created_{len(self.create_session_calls)}",
            "created_at": 1700000000.0,
        }

    async def publish_from_channel(self, event: EventEnvelope) -> None:
        self.published.append(event)

    async def send_user_input(
        self,
        session_id: str,
        content: str,
        attachments: list | None = None,
        context_files: list | None = None,
        meta: dict | None = None,
        source: str = "websocket",
    ) -> str:
        _ = (attachments, context_files, source)
        self.published.append(
            EventEnvelope(
                type=USER_INPUT,
                session_id=session_id,
                source="test",
                payload={
                    "content": content,
                    **({"meta": meta} if meta else {}),
                },
            )
        )
        return "turn_test"


class _FakeRepo:
    async def create_session(self, session_id: str, meta: dict | None = None) -> None:
        _ = (session_id, meta)

    async def get_session_events(self, session_id: str) -> list[dict]:
        _ = session_id
        return []

    async def list_sessions(self, limit: int = 50) -> list[dict]:
        _ = limit
        return []

    async def delete_session_cascade(self, session_id: str) -> None:
        _ = session_id

    async def update_session_title(self, session_id: str, title: str) -> None:
        _ = (session_id, title)

    async def get_session_messages(self, session_id: str) -> list[dict]:
        _ = session_id
        return []


@dataclass
class _FakeServices:
    repo: _FakeRepo
    gateway: _FakeGateway
    ws_channel: WebSocketChannel
    publisher: object
    auth_service: object | None = None


class _FakeWebSocket:
    """最小 WebSocket 替身：按顺序吐出消息，结束时抛 WebSocketDisconnect。"""

    def __init__(self, messages: list[dict]):
        self._messages = list(messages)
        self.sent_json: list[dict] = []
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def receive_json(self) -> dict:
        if self._messages:
            return self._messages.pop(0)
        raise WebSocketDisconnect()

    async def send_json(self, data: dict) -> None:
        self.sent_json.append(data)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        _ = (code, reason)


class _FakeClosingErrorWebSocket(_FakeWebSocket):
    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        _ = (code, reason)
        raise RuntimeError("Cannot call write() after write_eof()")


@pytest.fixture
def ws_env():
    old_services = getattr(gateway_main.app.state, "services", None)
    old_agent_registry = getattr(gateway_main.app.state, "agent_registry", None)

    fake = _FakeServices(
        repo=_FakeRepo(),
        gateway=_FakeGateway(),
        ws_channel=WebSocketChannel("websocket"),
        publisher=types.SimpleNamespace(),
        auth_service=None,
    )
    fake.ws_channel.gateway = fake.gateway
    gateway_main.app.state.services = fake
    gateway_main.app.state.agent_registry = types.SimpleNamespace(list_all=lambda: [])

    try:
        yield fake
    finally:
        if old_services is None:
            delattr(gateway_main.app.state, "services")
        else:
            gateway_main.app.state.services = old_services

        if old_agent_registry is None:
            delattr(gateway_main.app.state, "agent_registry")
        else:
            gateway_main.app.state.agent_registry = old_agent_registry


@pytest.mark.asyncio
async def test_user_input_with_existing_session_auto_binds_websocket(ws_env):
    ws = _FakeWebSocket(
        messages=[
            {
                "type": "user_input",
                "session_id": "sess_old",
                "payload": {"content": "hello", "attachments": [], "context_files": []},
            }
        ]
    )

    await gateway_main.websocket_endpoint(ws)

    assert ws.accepted is True
    assert ("sess_old", "websocket") in ws_env.gateway.bind_calls
    assert "sess_old" in ws_env.ws_channel._session_bindings
    assert any(e.type == USER_INPUT and e.session_id == "sess_old" for e in ws_env.gateway.published)


@pytest.mark.asyncio
async def test_create_session_echoes_request_id_to_frontend(ws_env):
    ws = _FakeWebSocket(
        messages=[
            {
                "type": "create_session",
                "payload": {
                    "agent_id": "research",
                    "meta": {"title": "调试会话"},
                    "request_id": "req_create_123",
                },
            }
        ]
    )

    await gateway_main.websocket_endpoint(ws)

    assert ws.accepted is True
    assert ws.sent_json[0]["type"] == "session_created"
    assert ws.sent_json[0]["payload"]["request_id"] == "req_create_123"
    assert ws_env.gateway.create_session_calls == [
        {
            "agent_id": "research",
            "meta": {"title": "调试会话"},
            "channel_id": "websocket",
        }
    ]


@pytest.mark.asyncio
async def test_invalid_websocket_token_close_runtime_error_is_swallowed(ws_env, monkeypatch):
    from sensenova_claw.platform.config.config import config
    from sensenova_claw.platform.security import middleware

    ws_env.ws_channel._auth_service = object()
    ws = _FakeClosingErrorWebSocket(messages=[])

    monkeypatch.setattr(config, "get", lambda key, default=None: True if key == "security.auth_enabled" else default)
    monkeypatch.setattr(middleware, "verify_websocket", lambda websocket, auth_service: False)

    await ws_env.ws_channel.handle_connection(ws)

    assert ws.accepted is True
    assert ws not in ws_env.ws_channel._connections


@pytest.mark.asyncio
async def test_user_question_answered_requires_session_id(ws_env):
    ws = _FakeWebSocket(
        messages=[
            {
                "type": "user_question_answered",
                "payload": {"question_id": "q1", "answer": "A", "cancelled": False},
            }
        ]
    )

    await gateway_main.websocket_endpoint(ws)

    assert any(msg.get("type") == "error" for msg in ws.sent_json)
    assert not any(e.type == USER_QUESTION_ANSWERED for e in ws_env.gateway.published)


@pytest.mark.asyncio
async def test_user_question_answered_requires_question_id(ws_env):
    ws = _FakeWebSocket(
        messages=[
            {
                "type": "user_question_answered",
                "session_id": "sess_q",
                "payload": {"answer": "A", "cancelled": False},
            }
        ]
    )

    await gateway_main.websocket_endpoint(ws)

    assert any(msg.get("type") == "error" for msg in ws.sent_json)
    assert not any(e.type == USER_QUESTION_ANSWERED for e in ws_env.gateway.published)


@pytest.mark.asyncio
async def test_user_question_asked_broadcasts_to_all_connections(ws_env):
    ws1 = _FakeWebSocket(messages=[])
    ws2 = _FakeWebSocket(messages=[])
    await ws_env.ws_channel.connect(ws1)
    await ws_env.ws_channel.connect(ws2)

    event = EventEnvelope(
        type=USER_QUESTION_ASKED,
        session_id="sess_any",
        source="test",
        payload={
            "question_id": "q_broadcast_1",
            "question": "请选择环境",
            "options": ["dev", "prod"],
            "multi_select": False,
            "timeout": 300,
            "source_agent_id": "research",
        },
    )
    ws_env.gateway.agent_registry = types.SimpleNamespace(
        get=lambda aid: types.SimpleNamespace(name="Research Agent") if aid == "research" else None
    )
    await ws_env.ws_channel.send_event(event)

    assert len(ws1.sent_json) == 1
    assert len(ws2.sent_json) == 1
    assert ws1.sent_json[0]["type"] == "user_question_asked"
    assert ws2.sent_json[0]["type"] == "user_question_asked"
    assert ws1.sent_json[0]["payload"]["question_id"] == "q_broadcast_1"
    assert ws2.sent_json[0]["payload"]["question_id"] == "q_broadcast_1"
    assert ws1.sent_json[0]["payload"]["source_agent_id"] == "research"
    assert ws1.sent_json[0]["payload"]["source_agent_name"] == "Research Agent"


@pytest.mark.asyncio
async def test_user_question_asked_source_agent_name_fallback_to_id(ws_env):
    ws = _FakeWebSocket(messages=[])
    await ws_env.ws_channel.connect(ws)

    ws_env.gateway.agent_registry = types.SimpleNamespace(get=lambda _aid: None)
    event = EventEnvelope(
        type=USER_QUESTION_ASKED,
        session_id="sess_any",
        source="test",
        payload={
            "question_id": "q_fallback_1",
            "question": "请选择环境",
            "options": ["dev", "prod"],
            "multi_select": False,
            "timeout": 300,
            "source_agent_id": "research",
        },
    )
    await ws_env.ws_channel.send_event(event)

    assert len(ws.sent_json) == 1
    assert ws.sent_json[0]["type"] == "user_question_asked"
    assert ws.sent_json[0]["payload"]["source_agent_id"] == "research"
    assert ws.sent_json[0]["payload"]["source_agent_name"] == "research"


@pytest.mark.asyncio
async def test_user_question_answered_event_broadcasts_to_all_connections(ws_env):
    ws1 = _FakeWebSocket(messages=[])
    ws2 = _FakeWebSocket(messages=[])
    await ws_env.ws_channel.connect(ws1)
    await ws_env.ws_channel.connect(ws2)

    event = EventEnvelope(
        type=USER_QUESTION_ANSWERED,
        session_id="sess_any",
        source="test",
        payload={"question_id": "q_done_1", "answer": "dev", "cancelled": False},
    )
    await ws_env.ws_channel.send_event(event)

    assert len(ws1.sent_json) == 1
    assert len(ws2.sent_json) == 1
    assert ws1.sent_json[0]["type"] == "user_question_answered_event"
    assert ws2.sent_json[0]["type"] == "user_question_answered_event"
    assert ws1.sent_json[0]["payload"]["question_id"] == "q_done_1"
    assert ws2.sent_json[0]["payload"]["question_id"] == "q_done_1"


@pytest.mark.asyncio
async def test_tool_confirmation_requested_broadcasts_to_all_connections(ws_env):
    ws1 = _FakeWebSocket(messages=[])
    ws2 = _FakeWebSocket(messages=[])
    await ws_env.ws_channel.connect(ws1)
    await ws_env.ws_channel.connect(ws2)

    event = EventEnvelope(
        type=TOOL_CONFIRMATION_REQUESTED,
        session_id="sess_child_confirm",
        source="test",
        payload={
            "tool_call_id": "tc_child_1",
            "tool_name": "bash_command",
            "arguments": {"command": "ls"},
            "risk_level": "high",
        },
    )
    await ws_env.ws_channel.send_event(event)

    assert len(ws1.sent_json) == 1
    assert len(ws2.sent_json) == 1
    assert ws1.sent_json[0]["type"] == "tool_confirmation_requested"
    assert ws2.sent_json[0]["type"] == "tool_confirmation_requested"
    assert ws1.sent_json[0]["payload"]["tool_call_id"] == "tc_child_1"
    assert ws2.sent_json[0]["payload"]["tool_call_id"] == "tc_child_1"


@pytest.mark.asyncio
async def test_tool_confirmation_requested_includes_timeout_fields(ws_env):
    ws = _FakeWebSocket(messages=[])
    await ws_env.ws_channel.connect(ws)

    event = EventEnvelope(
        type=TOOL_CONFIRMATION_REQUESTED,
        session_id="sess_child_confirm",
        source="test",
        payload={
            "tool_call_id": "tc_child_timeout",
            "tool_name": "bash_command",
            "arguments": {"command": "ls"},
            "risk_level": "high",
            "timeout": 60,
            "timeout_action": "approve",
            "requested_at_ms": 1700000000000,
        },
    )
    await ws_env.ws_channel.send_event(event)

    assert len(ws.sent_json) == 1
    assert ws.sent_json[0]["type"] == "tool_confirmation_requested"
    assert ws.sent_json[0]["payload"]["timeout"] == 60
    assert ws.sent_json[0]["payload"]["timeout_action"] == "approve"
    assert ws.sent_json[0]["payload"]["requested_at_ms"] == 1700000000000


@pytest.mark.asyncio
async def test_tool_confirmation_resolved_broadcasts_to_all_connections(ws_env):
    ws1 = _FakeWebSocket(messages=[])
    ws2 = _FakeWebSocket(messages=[])
    await ws_env.ws_channel.connect(ws1)
    await ws_env.ws_channel.connect(ws2)

    event = EventEnvelope(
        type=TOOL_CONFIRMATION_RESOLVED,
        session_id="sess_child_confirm",
        source="test",
        payload={
            "tool_call_id": "tc_child_2",
            "tool_name": "bash_command",
            "approved": True,
            "status": "approved",
            "reason": "timeout_approved",
            "resolved_by": "timeout",
            "resolved_at_ms": 1700000001234,
        },
    )
    await ws_env.ws_channel.send_event(event)

    assert len(ws1.sent_json) == 1
    assert len(ws2.sent_json) == 1
    assert ws1.sent_json[0]["type"] == "tool_confirmation_resolved"
    assert ws2.sent_json[0]["type"] == "tool_confirmation_resolved"
    assert ws1.sent_json[0]["payload"]["reason"] == "timeout_approved"
    assert ws2.sent_json[0]["payload"]["tool_call_id"] == "tc_child_2"


@pytest.mark.asyncio
async def test_proactive_result_broadcasts_to_all_connections_for_dashboard(ws_env):
    """proactive 推荐需要让工作台连接也能收到，而不依赖 session 绑定。"""
    ws1 = _FakeWebSocket(messages=[])
    ws2 = _FakeWebSocket(messages=[])
    await ws_env.ws_channel.connect(ws1)
    await ws_env.ws_channel.connect(ws2)

    event = EventEnvelope(
        type=PROACTIVE_RESULT,
        session_id="sess_recommendation",
        source="proactive",
        payload={
            "job_id": "builtin-turn-end-recommendation",
            "job_name": "会话推荐",
            "session_id": "sess_recommendation",
            "source_session_id": "sess_recommendation",
            "scratch_session_id": "sess_recommendation_scratch",
            "recommendation_type": "turn_end",
            "result": '{"recommendations":[{"id":"rec_1","title":"继续追问","prompt":"请继续分析","category":"follow-up"}]}',
            "items": [
                {
                    "id": "rec_1",
                    "title": "继续追问",
                    "prompt": "请继续分析",
                    "category": "follow-up",
                }
            ],
        },
    )

    await ws_env.ws_channel.send_event(event)

    assert len(ws1.sent_json) == 1
    assert len(ws2.sent_json) == 1
    assert ws1.sent_json[0]["type"] == "proactive_result"
    assert ws2.sent_json[0]["type"] == "proactive_result"
    assert ws1.sent_json[0]["payload"]["recommendation_type"] == "turn_end"
    assert ws2.sent_json[0]["payload"]["items"][0]["id"] == "rec_1"
    assert ws1.sent_json[0]["payload"]["scratch_session_id"] == "sess_recommendation_scratch"
