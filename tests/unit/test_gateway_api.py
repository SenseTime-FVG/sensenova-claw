"""Gateway API 端点单测 — 使用真实组件，无 mock"""
import asyncio
import pytest
from dataclasses import dataclass, field

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentos.adapters.plugins.whatsapp.models import WhatsAppRuntimeState
from agentos.interfaces.http.gateway import router
from agentos.interfaces.ws.gateway import Gateway
from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.runtime.publisher import EventPublisher
from agentos.adapters.storage.repository import Repository


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def app(tmp_path):
    """构建挂载真实 Gateway 和 Repository 的测试应用"""
    app = FastAPI()
    app.include_router(router)

    # 真实 PublicEventBus + EventPublisher + Gateway
    bus = PublicEventBus()
    publisher = EventPublisher(bus)
    gateway = Gateway(publisher)

    # 真实 Repository（临时 SQLite）
    repo = Repository(db_path=str(tmp_path / "test.db"))
    _run(repo.init())

    @dataclass
    class Services:
        gateway: Gateway
        repo: Repository
        publisher: EventPublisher

    services = Services(gateway=gateway, repo=repo, publisher=publisher)
    app.state.services = services
    app.state.config = type("Cfg", (), {"data": {"plugins": {"whatsapp": {"enabled": False}}}})()
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


# ── 统计 ──


def test_gateway_stats_empty(client):
    """无 channel / session 时统计为 0"""
    resp = client.get("/api/gateway/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["totalChannels"] == 0
    assert data["totalConnections"] == 0
    assert data["totalSessions"] == 0


def test_gateway_stats_with_sessions(client, app):
    """有 session 时统计正确"""
    # 直接向 repo 创建 session
    _run(app.state.services.repo.create_session("sess_a"))
    _run(app.state.services.repo.create_session("sess_b"))

    # 向 gateway 绑定 session（模拟 channel 注册）
    gw = app.state.services.gateway
    gw._session_bindings["sess_a"] = "websocket_1"

    resp = client.get("/api/gateway/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["totalSessions"] == 2
    assert data["totalConnections"] == 1  # 只有 1 个 session_binding


# ── Channels 列表 ──


def test_list_channels_empty(client):
    """无 channel 时返回空列表"""
    resp = client.get("/api/gateway/channels")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_channels_with_data(client, app):
    """有 channel 时正常列出"""
    # 直接往 _channels 字典中插入（避免需要真实 Channel 实例）
    gw = app.state.services.gateway
    gw._channels["websocket_1"] = object()  # 占位
    gw._channels["cli_2"] = object()

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
    gw = app.state.services.gateway
    gw._channels["websocket"] = object()
    resp = client.get("/api/gateway/channels")
    data = resp.json()
    assert len(data) == 1
    assert data[0]["type"] == "websocket"
    assert data[0]["id"] == "websocket"


def test_list_channels_marks_telegram_failed_when_runtime_has_error(client, app):
    gw = app.state.services.gateway

    class _Runtime:
        _agentos_status = {"status": "failed", "error": "polling failed"}

    class _Channel:
        _runtime = _Runtime()

    gw._channels["telegram"] = _Channel()

    resp = client.get("/api/gateway/channels")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["id"] == "telegram"
    assert data[0]["status"] == "failed"


def test_list_channels_marks_wecom_failed_when_client_has_error(client, app):
    gw = app.state.services.gateway

    class _Client:
        _agentos_status = {"status": "failed", "error": "websocket closed"}

    class _Channel:
        _client = _Client()

    gw._channels["wecom"] = _Channel()

    resp = client.get("/api/gateway/channels")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["id"] == "wecom"
    assert data[0]["status"] == "failed"


def test_list_channels_marks_feishu_failed_when_channel_has_error(client, app):
    gw = app.state.services.gateway

    class _Channel:
        _agentos_status = {"status": "failed", "error": "websocket thread crashed"}

    gw._channels["feishu"] = _Channel()

    resp = client.get("/api/gateway/channels")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["id"] == "feishu"
    assert data[0]["status"] == "failed"


def test_whatsapp_status_disabled(client):
    resp = client.get("/api/gateway/whatsapp/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False
    assert data["authorized"] is False
    assert data["state"] == "not_initialized"
    assert data["authDir"] is None


def test_whatsapp_status_ready(client, app):
    app.state.config.data["plugins"]["whatsapp"]["enabled"] = True
    app.state.config.data["plugins"]["whatsapp"]["auth_dir"] = "/tmp/wa-auth"

    class _Channel:
        _runtime_state = WhatsAppRuntimeState(
            state="ready",
            connected=True,
            phone="+15550000001",
            last_qr="qr-text",
            last_qr_data_url="data:image/png;base64,abc",
            last_event="open",
            debug_message="connection open",
        )

    app.state.services.gateway._channels["whatsapp"] = _Channel()
    resp = client.get("/api/gateway/whatsapp/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["authorized"] is True
    assert data["state"] == "ready"
    assert data["phone"] == "+15550000001"
    assert data["lastQrDataUrl"] == "data:image/png;base64,abc"
    assert data["authDir"] == "/tmp/wa-auth"
    assert data["lastEvent"] == "open"
    assert data["debugMessage"] == "connection open"


def test_whatsapp_status_exposes_detailed_error_and_auth_dir(client, app):
    app.state.config.data["plugins"]["whatsapp"]["enabled"] = True
    app.state.config.data["plugins"]["whatsapp"]["auth_dir"] = "/tmp/wa-auth"

    class _Channel:
        _runtime_state = WhatsAppRuntimeState(
            state="closed",
            connected=False,
            last_error='Connection Failure | statusCode=405 | payload={"reason":"405","location":"cln"}',
            last_status_code=405,
            last_event="error",
            debug_message="connection closed before ready",
        )

    app.state.services.gateway._channels["whatsapp"] = _Channel()
    resp = client.get("/api/gateway/whatsapp/status")
    data = resp.json()
    assert data["authorized"] is False
    assert data["state"] == "closed"
    assert "statusCode=405" in data["lastError"]
    assert data["authDir"] == "/tmp/wa-auth"
    assert data["lastStatusCode"] == 405
    assert data["lastEvent"] == "error"
    assert data["debugMessage"] == "connection closed before ready"
