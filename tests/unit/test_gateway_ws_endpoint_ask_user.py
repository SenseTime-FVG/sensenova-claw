"""WebSocket endpoint 的 ask_user 相关单测（无真实端口依赖）。"""

from __future__ import annotations

import types
from dataclasses import dataclass

import pytest
from fastapi import WebSocketDisconnect

from agentos.app.gateway import main as gateway_main
from agentos.adapters.channels.websocket_channel import WebSocketChannel
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import USER_INPUT, USER_QUESTION_ANSWERED, USER_QUESTION_ASKED


class _FakeGateway:
    def __init__(self):
        self.bind_calls: list[tuple[str, str]] = []
        self.published: list[EventEnvelope] = []
        self.agent_registry = types.SimpleNamespace(get=lambda _aid: None)

    def bind_session(self, session_id: str, channel_id: str) -> None:
        self.bind_calls.append((session_id, channel_id))

    async def publish_from_channel(self, event: EventEnvelope) -> None:
        self.published.append(event)

    async def send_user_input(
        self,
        session_id: str,
        content: str,
        attachments: list | None = None,
        context_files: list | None = None,
        source: str = "websocket",
    ) -> str:
        _ = (attachments, context_files, source)
        self.published.append(
            EventEnvelope(
                type=USER_INPUT,
                session_id=session_id,
                source="test",
                payload={"content": content},
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
