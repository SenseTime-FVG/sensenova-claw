"""Config API 端点单测 — 使用真实 Config，无 mock"""
import pytest
import yaml
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentos.interfaces.http import config_api
from agentos.interfaces.http.config_api import router
from agentos.platform.config.config import Config
from agentos.platform.config.config_manager import ConfigManager
from agentos.platform.secrets.store import InMemorySecretStore
from agentos.kernel.events.bus import PublicEventBus


@pytest.fixture
def app(tmp_path):
    """构建挂载真实 Config 的测试应用"""
    app = FastAPI()
    app.include_router(router)

    config_path = tmp_path / "config.yml"
    initial = {
        "llm": {
            "providers": {"openai": {"api_key": "sk-xxx"}},
            "models": {"gpt-5.4": {"provider": "openai", "model_id": "gpt-5.4"}},
            "default_model": "gpt-5.4",
        },
        "agent": {"model": "gpt-5.4", "temperature": 0.2},
        "plugins": {},
    }
    config_path.write_text(yaml.dump(initial), encoding="utf-8")

    secret_store = InMemorySecretStore()
    cfg = Config(config_path=config_path, secret_store=secret_store)
    bus = PublicEventBus()
    config_manager = ConfigManager(config=cfg, event_bus=bus, secret_store=secret_store)
    app.state.config = cfg
    app.state.secret_store = secret_store
    app.state.config_manager = config_manager
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


# ── 获取 sections ──


def test_get_sections(client):
    """正常获取三个可编辑 section"""
    resp = client.get("/api/config/sections")
    assert resp.status_code == 200
    data = resp.json()
    assert "llm" in data
    assert "agent" in data
    assert "plugins" in data
    assert data["agent"]["model"] == "gpt-5.4"
    assert data["llm"]["providers"]["openai"]["api_key"]["configured"] is True
    assert data["llm"]["providers"]["openai"]["api_key"]["source"] == "plain"


def test_get_sections_has_defaults(client, app):
    """config.data 中的 section 返回合并后的默认值"""
    resp = client.get("/api/config/sections")
    assert resp.status_code == 200
    data = resp.json()
    assert "plugins" in data


# ── 更新 sections ──


def test_update_sections(client, app):
    """正常更新 agent section"""
    resp = client.put("/api/config/sections", json={
        "agent": {"model": "claude-opus", "temperature": 0.5},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "saved"
    assert "sections" in data
    raw = app.state.config._config_path.read_text(encoding="utf-8")
    written = yaml.safe_load(raw)
    assert written["agent"]["model"] == "claude-opus"


def test_update_sections_multiple(client, app):
    """同时更新多个 section"""
    resp = client.put("/api/config/sections", json={
        "llm": {"providers": {"anthropic": {"api_key": "sk-yyy"}}},
        "plugins": {"search": {"enabled": True}},
    })
    assert resp.status_code == 200
    raw = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    assert raw["llm"]["providers"]["anthropic"]["api_key"] == (
        "${secret:agentos/llm.providers.anthropic.api_key}"
    )
    assert app.state.secret_store.get("agentos/llm.providers.anthropic.api_key") == "sk-yyy"
    assert raw["plugins"]["search"]["enabled"] is True
    sections = resp.json()["sections"]
    assert sections["llm"]["providers"]["anthropic"]["api_key"]["configured"] is True
    assert sections["llm"]["providers"]["anthropic"]["api_key"]["source"] == "secret"


def test_update_sections_empty_body(client):
    """未提供任何更新内容时返回 400"""
    resp = client.put("/api/config/sections", json={})
    assert resp.status_code == 400


def test_update_sections_preserves_other_keys(client, app):
    """更新不会覆盖 config.yml 中已有的其他顶层 key"""
    raw = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    raw["custom_key"] = "keep_me"
    app.state.config._config_path.write_text(yaml.dump(raw), encoding="utf-8")

    resp = client.put("/api/config/sections", json={
        "agent": {"model": "test"},
    })
    assert resp.status_code == 200
    written = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    assert written["custom_key"] == "keep_me"


def test_list_models_accepts_openai_compatible_provider_keys(client, monkeypatch):
    """OpenAI 兼容 provider 应透传具体 key，后端仍按 OpenAI 兼容方式处理"""
    mocked = AsyncMock(return_value=[
        {"id": "MiniMax-M2.7-highspeed", "owned_by": "minimax"},
    ])
    monkeypatch.setattr(config_api, "_list_models_openai", mocked)

    resp = client.post("/api/config/list-models", json={
        "provider": "minimax",
        "api_key": "sk-minimax",
        "base_url": "https://api.minimax.chat/v1",
    })

    assert resp.status_code == 200
    assert resp.json() == {
        "success": True,
        "models": [{"id": "MiniMax-M2.7-highspeed", "owned_by": "minimax"}],
    }
    mocked.assert_awaited_once_with("sk-minimax", "https://api.minimax.chat/v1")
