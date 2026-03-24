"""工具 API key 管理单元测试。"""

from __future__ import annotations

import yaml
import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sensenova_claw.capabilities.tools.registry import ToolRegistry
from sensenova_claw.interfaces.http.tools import router, VALIDATORS
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.platform.config.config import Config
from sensenova_claw.platform.config.config_manager import ConfigManager
from sensenova_claw.platform.secrets.store import InMemorySecretStore


@pytest.fixture
def app(tmp_path):
    app = FastAPI()
    app.include_router(router)

    config_path = tmp_path / "config.yml"
    initial = {
        "tools": {
            "serper_search": {"api_key": "sk-serper-12345678"},
            "brave_search": {"api_key": ""},
            "baidu_search": {"api_key": ""},
            "tavily_search": {"api_key": ""},
        },
    }
    config_path.write_text(yaml.dump(initial), encoding="utf-8")

    secret_store = InMemorySecretStore()
    cfg = Config(config_path=config_path, secret_store=secret_store)
    bus = PublicEventBus()
    config_manager = ConfigManager(config=cfg, event_bus=bus, secret_store=secret_store)
    app.state.config = cfg
    app.state.tool_registry = ToolRegistry()
    app.state.sensenova_claw_home = str(tmp_path)
    app.state.secret_store = secret_store
    app.state.config_manager = config_manager
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_get_api_key_status_masks_existing_key(client):
    response = client.get("/api/tools/api-keys")
    assert response.status_code == 200
    data = response.json()
    assert data["serper_search"]["configured"] is True
    assert data["serper_search"]["masked_key"].startswith("sk-s")
    assert data["serper_search"]["source"] == "plain"
    assert data["brave_search"]["configured"] is False
    assert data["brave_search"]["source"] == "empty"


def test_get_api_key_status_includes_detailed_setup_guides(client):
    response = client.get("/api/tools/api-keys")
    assert response.status_code == 200

    data = response.json()
    assert "Dashboard" in "\n".join(data["serper_search"]["setup_guide"])
    assert "X-Subscription-Token" in "\n".join(data["brave_search"]["setup_guide"])
    assert "Bearer" in "\n".join(data["baidu_search"]["setup_guide"])
    assert "Authorization: Bearer" in "\n".join(data["tavily_search"]["setup_guide"])
    assert data["baidu_search"]["example_format"].startswith("bce-v3/")


def test_put_api_keys_persists_to_config(client, app):
    response = client.put("/api/tools/api-keys", json={
        "brave_search": "BSA-new-key-1234",
        "tavily_search": "tvly-new-key-9999",
    })
    assert response.status_code == 200

    written = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    assert written["tools"]["brave_search"]["api_key"] == "${secret:sensenova_claw/tools.brave_search.api_key}"
    assert written["tools"]["tavily_search"]["api_key"] == "${secret:sensenova_claw/tools.tavily_search.api_key}"
    assert app.state.secret_store.get("sensenova_claw/tools.brave_search.api_key") == "BSA-new-key-1234"
    assert app.state.secret_store.get("sensenova_claw/tools.tavily_search.api_key") == "tvly-new-key-9999"

    data = response.json()["api_keys"]
    assert data["brave_search"]["configured"] is True
    assert data["tavily_search"]["configured"] is True
    assert data["brave_search"]["source"] == "secret"
    assert data["tavily_search"]["source"] == "secret"


def test_validate_api_key_endpoint_uses_validator(client, monkeypatch):
    async def fake_validator(api_key: str):
        assert api_key == "candidate-key"
        return True, "validator-ok"

    monkeypatch.setitem(VALIDATORS, "serper_search", fake_validator)

    response = client.post("/api/tools/api-keys/serper_search/validate", json={"api_key": "candidate-key"})
    assert response.status_code == 200
    assert response.json() == {"valid": True, "message": "validator-ok"}
