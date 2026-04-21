"""Config API 端点单测 — 使用真实 Config，无 mock"""
import pytest
import yaml
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sensenova_claw.interfaces.http import config_api
from sensenova_claw.interfaces.http.config_api import router
from sensenova_claw.platform.config.config import Config
from sensenova_claw.platform.config.config_manager import ConfigManager
from sensenova_claw.platform.secrets.store import InMemorySecretStore
from sensenova_claw.kernel.events.bus import PublicEventBus


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
    """正常获取四个可编辑 section"""
    resp = client.get("/api/config/sections")
    assert resp.status_code == 200
    data = resp.json()
    assert "llm" in data
    assert "agent" in data
    assert "plugins" in data
    assert "miniapps" in data
    assert data["agent"]["model"] == "gpt-5.4"
    assert data["llm"]["providers"]["openai"]["api_key"]["configured"] is True
    assert data["llm"]["providers"]["openai"]["api_key"]["source"] == "plain"
    assert data["llm"]["_meta"]["explicit_provider_names"] == ["openai"]
    assert data["miniapps"]["default_builder"] == "builtin"
    assert data["miniapps"]["acp"]["request_timeout_seconds"] == 180


def test_get_sections_has_defaults(client, app):
    """config.data 中的 section 返回合并后的默认值"""
    resp = client.get("/api/config/sections")
    assert resp.status_code == 200
    data = resp.json()
    assert "plugins" in data
    assert "miniapps" in data


def test_get_acp_wizard_returns_detected_agents(client):
    resp = client.get("/api/config/acp/wizard")

    assert resp.status_code == 200
    data = resp.json()
    assert data["platform"]["id"] in {"linux", "macos", "windows"}
    ids = {item["id"] for item in data["agents"]}
    assert {"codex", "claude", "gemini", "kimi", "opencode", "codex-bridge"} <= ids


def test_install_acp_wizard_uses_injected_service(client, app):
    class FakeWizard:
        def __init__(self) -> None:
            self.calls: list[tuple[str, list[str], dict]] = []

        async def install(self, agent_id: str, *, step_ids: list[str] | None = None, current_config: dict | None = None):
            self.calls.append((agent_id, step_ids or [], current_config or {}))
            return {
                "ok": True,
                "agent_id": agent_id,
                "executed_steps": [],
                "wizard": {"platform": {"id": "linux", "label": "Linux", "python": "/usr/bin/python3"}, "installers": {}, "agents": [], "current_config": {}},
            }

    fake = FakeWizard()
    app.state.acp_wizard_service = fake

    resp = client.post("/api/config/acp/wizard/install", json={
        "agent_id": "gemini",
        "step_ids": ["agent"],
    })

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert fake.calls == [("gemini", ["agent"], {"enabled": False, "command": "", "args": [], "env": {}, "startup_timeout_seconds": 20, "request_timeout_seconds": 180})]


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
        "miniapps": {
            "default_builder": "acp",
            "acp": {
                "enabled": True,
                "command": "codex",
                "args": ["--stdio"],
                "env": {"OPENAI_API_KEY": "sk-acp"},
                "startup_timeout_seconds": 45,
                "request_timeout_seconds": 240,
            },
        },
    })
    assert resp.status_code == 200
    raw = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    assert raw["llm"]["providers"]["anthropic"]["api_key"] == (
        "${secret:sensenova_claw/llm.providers.anthropic.api_key}"
    )
    assert app.state.secret_store.get("sensenova_claw/llm.providers.anthropic.api_key") == "sk-yyy"
    assert raw["plugins"]["search"]["enabled"] is True
    assert raw["miniapps"]["default_builder"] == "acp"
    assert raw["miniapps"]["acp"]["enabled"] is True
    assert raw["miniapps"]["acp"]["command"] == "codex"
    assert raw["miniapps"]["acp"]["args"] == ["--stdio"]
    assert raw["miniapps"]["acp"]["env"] == {"OPENAI_API_KEY": "sk-acp"}
    assert raw["miniapps"]["acp"]["startup_timeout_seconds"] == 45
    assert raw["miniapps"]["acp"]["request_timeout_seconds"] == 240
    sections = resp.json()["sections"]
    assert sections["llm"]["providers"]["anthropic"]["api_key"]["configured"] is True
    assert sections["llm"]["providers"]["anthropic"]["api_key"]["source"] == "secret"
    assert sections["miniapps"]["default_builder"] == "acp"
    assert sections["miniapps"]["acp"]["enabled"] is True
    assert sections["miniapps"]["acp"]["command"] == "codex"


def test_update_sections_preserves_env_ref_for_sensitive_value(client, app):
    """批量保存 section 时，环境变量引用应保持原样。"""
    raw = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    raw["llm"]["providers"]["openai"]["api_key"] = "${OPENAI_API_KEY}"
    app.state.config._config_path.write_text(yaml.dump(raw), encoding="utf-8")
    app.state.config.data = app.state.config._load_config()

    resp = client.put("/api/config/sections", json={
        "llm": {
            "providers": {
                "openai": {
                    "api_key": "${OPENAI_API_KEY}",
                    "base_url": "https://api.openai.com/v1",
                }
            }
        }
    })

    assert resp.status_code == 200
    written = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    assert written["llm"]["providers"]["openai"]["api_key"] == "${OPENAI_API_KEY}"
    assert app.state.secret_store.get("sensenova_claw/llm.providers.openai.api_key") is None


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


def test_update_llm_model_persists_missing_provider_placeholder(client, app):
    """当模型引用尚未落盘的 provider 时，保存模型应同时保留该 provider 占位配置。"""
    resp = client.put("/api/config/llm/models/test-model", json={
        "name": "test-model",
        "provider": "custom-openai",
        "model_id": "gpt-4.1-mini",
        "type": "chat",
        "timeout": 60,
        "max_tokens": 128000,
        "max_output_tokens": 16384,
    })

    assert resp.status_code == 200
    written = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    assert written["llm"]["providers"]["custom-openai"] == {
        "source_type": "openai",
        "base_url": "",
        "timeout": 60,
        "max_retries": 3,
        "api_key": "",
    }
    assert written["llm"]["models"]["test-model"]["provider"] == "custom-openai"


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


def test_get_secret_reveals_sensitive_value(client):
    """通用 secret reveal API 返回敏感路径的真实值。"""
    resp = client.get("/api/config/secret", params={"path": "llm.providers.openai.api_key"})
    assert resp.status_code == 200
    assert resp.json() == {"path": "llm.providers.openai.api_key", "value": "sk-xxx"}


def test_get_secret_reveals_secret_store_value_when_raw_yaml_uses_secret_ref(client, app):
    """当 config.yml 中保存的是 `${secret:...}` 时，reveal API 仍应返回 secret store 中的明文。"""
    raw = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    raw["llm"]["providers"]["openai"]["api_key"] = "${secret:sensenova_claw/llm.providers.openai.api_key}"
    app.state.config._config_path.write_text(yaml.dump(raw), encoding="utf-8")
    app.state.secret_store.set("sensenova_claw/llm.providers.openai.api_key", "sk-from-store")
    app.state.config.data = app.state.config._load_config()

    resp = client.get("/api/config/secret", params={"path": "llm.providers.openai.api_key"})

    assert resp.status_code == 200
    assert resp.json() == {"path": "llm.providers.openai.api_key", "value": "sk-from-store"}


def test_get_secret_rejects_non_secret_path(client):
    """非敏感路径不能通过 reveal API 读取。"""
    resp = client.get("/api/config/secret", params={"path": "agent.model"})
    assert resp.status_code == 400


def test_update_single_provider_and_rename_models(client, app):
    """单项更新 provider 时允许改名，并联动迁移其下模型的 provider 引用。"""
    raw = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    raw["llm"]["providers"]["openai"]["base_url"] = "https://api.openai.com/v1"
    raw["llm"]["providers"]["openai"]["timeout"] = 60
    raw["llm"]["providers"]["openai"]["max_retries"] = 3
    raw["llm"]["providers"]["openai"]["source_type"] = "openai"
    raw["llm"]["models"]["gpt-4o-mini"] = {
        "provider": "openai",
        "model_id": "gpt-4o-mini",
        "timeout": 60,
        "max_output_tokens": 8192,
    }
    app.state.config._config_path.write_text(yaml.dump(raw), encoding="utf-8")
    app.state.config.data = app.state.config._load_config()

    resp = client.put("/api/config/llm/providers/openai", json={
        "name": "openai-compatible",
        "source_type": "openai-compatible",
        "base_url": "https://proxy.example.com/v1",
        "timeout": 90,
        "max_retries": 5,
    })

    assert resp.status_code == 200
    written = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    assert "openai-compatible" in written["llm"]["providers"]
    assert "openai" not in written["llm"]["providers"]
    assert written["llm"]["providers"]["openai-compatible"]["source_type"] == "openai-compatible"
    assert written["llm"]["providers"]["openai-compatible"]["base_url"] == "https://proxy.example.com/v1"
    assert written["llm"]["models"]["gpt-4o-mini"]["provider"] == "openai-compatible"


def test_update_single_provider_does_not_persist_secret_ref_placeholder_as_api_key(client, app):
    """前端误传 `${secret:...}` 占位符时，后端不应把占位符写入 secret store。"""
    raw = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    raw["llm"]["providers"]["openai"]["api_key"] = "${secret:sensenova_claw/llm.providers.openai.api_key}"
    raw["llm"]["providers"]["openai"]["base_url"] = "https://api.openai.com/v1"
    raw["llm"]["providers"]["openai"]["timeout"] = 60
    raw["llm"]["providers"]["openai"]["max_retries"] = 3
    raw["llm"]["providers"]["openai"]["source_type"] = "openai"
    app.state.config._config_path.write_text(yaml.dump(raw), encoding="utf-8")
    app.state.secret_store.set("sensenova_claw/llm.providers.openai.api_key", "sk-real")
    app.state.config.data = app.state.config._load_config()

    resp = client.put("/api/config/llm/providers/openai", json={
        "name": "openai",
        "source_type": "openai",
        "api_key": "${secret:sensenova_claw/llm.providers.openai.api_key}",
        "base_url": "https://api.openai.com/v1",
        "timeout": 60,
        "max_retries": 3,
    })

    assert resp.status_code == 200
    written = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    assert written["llm"]["providers"]["openai"]["api_key"] == "${secret:sensenova_claw/llm.providers.openai.api_key}"
    assert app.state.secret_store.get("sensenova_claw/llm.providers.openai.api_key") == "sk-real"


def test_update_single_provider_preserves_env_ref_api_key(client, app):
    """单项保存 provider 时，环境变量引用应保持原样，不改写为 secret 引用。"""
    raw = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    raw["llm"]["providers"]["openai"]["api_key"] = "${OPENAI_API_KEY}"
    raw["llm"]["providers"]["openai"]["base_url"] = "https://api.openai.com/v1"
    raw["llm"]["providers"]["openai"]["timeout"] = 60
    raw["llm"]["providers"]["openai"]["max_retries"] = 3
    raw["llm"]["providers"]["openai"]["source_type"] = "openai"
    app.state.config._config_path.write_text(yaml.dump(raw), encoding="utf-8")
    app.state.config.data = app.state.config._load_config()

    resp = client.put("/api/config/llm/providers/openai", json={
        "name": "openai",
        "source_type": "openai",
        "api_key": "${OPENAI_API_KEY}",
        "base_url": "https://api.openai.com/v1",
        "timeout": 60,
        "max_retries": 3,
    })

    assert resp.status_code == 200
    written = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    assert written["llm"]["providers"]["openai"]["api_key"] == "${OPENAI_API_KEY}"
    assert app.state.secret_store.get("sensenova_claw/llm.providers.openai.api_key") is None


def test_create_single_provider_when_missing(client, app):
    """单项保存新 provider 时，后端应按 upsert 方式创建而不是返回 404。"""
    resp = client.put("/api/config/llm/providers/deepseek", json={
        "name": "deepseek",
        "source_type": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "timeout": 60,
        "max_retries": 3,
        "api_key": "sk-deepseek",
    })

    assert resp.status_code == 200
    written = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    assert written["llm"]["providers"]["deepseek"]["source_type"] == "deepseek"
    assert written["llm"]["providers"]["deepseek"]["base_url"] == "https://api.deepseek.com/v1"
    assert written["llm"]["providers"]["deepseek"]["timeout"] == 60
    assert written["llm"]["providers"]["deepseek"]["max_retries"] == 3
    assert written["llm"]["providers"]["deepseek"]["api_key"] == "${secret:sensenova_claw/llm.providers.deepseek.api_key}"
    assert app.state.secret_store.get("sensenova_claw/llm.providers.deepseek.api_key") == "sk-deepseek"


def test_update_single_model_and_rename_default_model(client, app):
    """单项更新 llm 时允许改名，并联动 default_model。"""
    raw = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    raw["llm"]["models"]["gpt-4o-mini"] = {
        "provider": "openai",
        "model_id": "gpt-4o-mini",
        "timeout": 60,
        "max_output_tokens": 8192,
    }
    raw["llm"]["default_model"] = "gpt-4o-mini"
    app.state.config._config_path.write_text(yaml.dump(raw), encoding="utf-8")
    app.state.config.data = app.state.config._load_config()

    resp = client.put("/api/config/llm/models/gpt-4o-mini", json={
        "name": "gpt-4.1-mini",
        "provider": "openai",
        "model_id": "gpt-4.1-mini",
        "timeout": 75,
        "max_output_tokens": 16384,
    })

    assert resp.status_code == 200
    written = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    assert "gpt-4.1-mini" in written["llm"]["models"]
    assert "gpt-4o-mini" not in written["llm"]["models"]
    assert written["llm"]["models"]["gpt-4.1-mini"]["model_id"] == "gpt-4.1-mini"
    assert written["llm"]["default_model"] == "gpt-4.1-mini"


def test_create_single_model_when_missing(client, app):
    """单项保存新 llm 时，后端应按 upsert 方式创建而不是返回 404。"""
    resp = client.put("/api/config/llm/models/deepseek-chat", json={
        "name": "deepseek-chat",
        "provider": "openai",
        "model_id": "deepseek-chat",
        "timeout": 45,
        "max_tokens": 64000,
        "max_output_tokens": 8192,
    })

    assert resp.status_code == 200
    written = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    assert written["llm"]["models"]["deepseek-chat"] == {
        "provider": "openai",
        "model_id": "deepseek-chat",
        "type": "chat",
        "timeout": 45,
        "max_tokens": 64000,
        "max_output_tokens": 8192,
    }


def test_update_default_model_only(client, app):
    """单项更新 default_model 时只修改默认模型字段。"""
    raw = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    raw["llm"]["models"]["gpt-4o-mini"] = {
        "provider": "openai",
        "model_id": "gpt-4o-mini",
        "timeout": 60,
        "max_output_tokens": 8192,
    }
    raw["llm"]["default_model"] = "gpt-5.4"
    app.state.config._config_path.write_text(yaml.dump(raw), encoding="utf-8")
    app.state.config.data = app.state.config._load_config()

    resp = client.put("/api/config/llm/default-model", json={
        "default_model": "gpt-4o-mini",
    })

    assert resp.status_code == 200
    written = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    assert written["llm"]["default_model"] == "gpt-4o-mini"
    assert "gpt-5.4" in written["llm"]["models"]
    assert "gpt-4o-mini" in written["llm"]["models"]


# ── 必配清单检查 ──


def test_required_check_all_missing(client):
    """未配置搜索工具和邮箱时，两项都返回 configured=false"""
    resp = client.get("/api/config/required-check")
    assert resp.status_code == 200
    data = resp.json()
    assert data["search_tool"]["configured"] is False
    assert data["email"]["configured"] is False


def test_required_check_search_configured(client, app):
    """配置了搜索工具 API key 后，search_tool 返回 configured=true"""
    app.state.config.data.setdefault("tools", {}).setdefault("serper_search", {})["api_key"] = "sk-test"
    resp = client.get("/api/config/required-check")
    data = resp.json()
    assert data["search_tool"]["configured"] is True
    assert data["email"]["configured"] is False
