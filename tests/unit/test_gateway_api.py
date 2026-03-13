"""Gateway API 端点单测（使用 TestClient + mock app.state）"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentos.interfaces.http.gateway import router


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)

    # mock gateway
    mock_channel = MagicMock()
    gateway = MagicMock()
    gateway._channels = {"websocket_1": mock_channel, "cli_2": MagicMock()}
    gateway._session_bindings = {"sess_a": "websocket_1", "sess_b": "cli_2"}

    # mock repo
    repo = AsyncMock()
    repo.list_sessions.return_value = [
        {"session_id": "sess_a"},
        {"session_id": "sess_b"},
        {"session_id": "sess_c"},
    ]

    services = MagicMock()
    services.gateway = gateway
    services.repo = repo

    app.state.services = services
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


# ── 统计 ──


def test_gateway_stats(client):
    """正常获取 Gateway 统计信息"""
    resp = client.get("/api/gateway/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["totalChannels"] == 2
    assert data["activeChannels"] == 2
    assert data["totalConnections"] == 2
    assert data["totalSessions"] == 3


def test_gateway_stats_empty(client, app):
    """无 channel / session 时统计为 0"""
    app.state.services.gateway._channels = {}
    app.state.services.gateway._session_bindings = {}
    app.state.services.repo.list_sessions.return_value = []

    resp = client.get("/api/gateway/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["totalChannels"] == 0
    assert data["totalConnections"] == 0
    assert data["totalSessions"] == 0


# ── Channels 列表 ──


def test_list_channels(client):
    """正常列出所有 Channels"""
    resp = client.get("/api/gateway/channels")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    ids = {ch["id"] for ch in data}
    assert "websocket_1" in ids
    assert "cli_2" in ids
    # 验证 type 按 _ 拆分
    ws_ch = [ch for ch in data if ch["id"] == "websocket_1"][0]
    assert ws_ch["type"] == "websocket"
    cli_ch = [ch for ch in data if ch["id"] == "cli_2"][0]
    assert cli_ch["type"] == "cli"


def test_list_channels_no_underscore(client, app):
    """channel_id 不含下划线时 type 等于 id"""
    app.state.services.gateway._channels = {"websocket": MagicMock()}
    resp = client.get("/api/gateway/channels")
    data = resp.json()
    assert len(data) == 1
    assert data[0]["type"] == "websocket"
    assert data[0]["id"] == "websocket"


def test_list_channels_empty(client, app):
    """无 channel 时返回空列表"""
    app.state.services.gateway._channels = {}
    resp = client.get("/api/gateway/channels")
    assert resp.status_code == 200
    assert resp.json() == []
