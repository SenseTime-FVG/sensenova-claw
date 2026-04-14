"""MCP API 端点单测。"""
from __future__ import annotations

import yaml
import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sensenova_claw.interfaces.http.mcp import router
from sensenova_claw.platform.config.config import Config
from sensenova_claw.platform.config.config_manager import ConfigManager
from sensenova_claw.platform.secrets.store import InMemorySecretStore
from sensenova_claw.kernel.events.bus import PublicEventBus


@pytest.fixture
def app(tmp_path):
    app = FastAPI()
    app.include_router(router)

    config_path = tmp_path / "config.yml"
    initial = {
        "mcp": {
            "servers": {
                "browsermcp": {
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["@browsermcp/mcp@latest"],
                    "timeout": 15,
                }
            }
        }
    }
    config_path.write_text(yaml.dump(initial, allow_unicode=True, sort_keys=False), encoding="utf-8")

    secret_store = InMemorySecretStore()
    cfg = Config(config_path=config_path, secret_store=secret_store)
    bus = PublicEventBus()
    config_manager = ConfigManager(config=cfg, event_bus=bus, secret_store=secret_store)
    app.state.config = cfg
    app.state.config_manager = config_manager
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_list_mcp_servers(client):
    resp = client.get("/api/mcp/servers")
    assert resp.status_code == 200
    data = resp.json()
    assert "servers" in data
    assert data["servers"][0]["name"] == "browsermcp"
    assert data["servers"][0]["transport"] == "stdio"
    assert data["servers"][0]["command"] == "npx"
    assert data["servers"][0]["args"] == ["@browsermcp/mcp@latest"]


def test_save_mcp_servers(client, app):
    resp = client.put(
        "/api/mcp/servers",
        json={
            "servers": [
                {
                    "name": "browsermcp",
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["@browsermcp/mcp@latest"],
                    "env": [{"key": "MCP_TOKEN", "value": "${MCP_TOKEN}"}],
                    "timeout": 20,
                },
                {
                    "name": "docs-search",
                    "transport": "streamable-http",
                    "url": "http://127.0.0.1:3101/mcp",
                    "headers": [{"key": "Authorization", "value": "Bearer ${DOCS_MCP_TOKEN}"}],
                    "timeout": 30,
                },
            ]
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["servers"]) == 2

    written = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    assert written["mcp"]["servers"]["browsermcp"]["command"] == "npx"
    assert written["mcp"]["servers"]["browsermcp"]["env"] == {"MCP_TOKEN": "${MCP_TOKEN}"}
    assert written["mcp"]["servers"]["docs-search"]["transport"] == "streamable-http"
    assert written["mcp"]["servers"]["docs-search"]["headers"] == {
        "Authorization": "Bearer ${DOCS_MCP_TOKEN}",
    }


def test_save_mcp_servers_rejects_invalid_stdio(client):
    resp = client.put(
        "/api/mcp/servers",
        json={
            "servers": [
                {
                    "name": "broken",
                    "transport": "stdio",
                    "command": "",
                }
            ]
        },
    )
    assert resp.status_code == 400
    assert "command" in resp.json()["detail"]
