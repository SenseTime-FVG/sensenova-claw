"""Config API 端点单测 — 使用真实 Config，无 mock"""
import pytest
import yaml
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentos.interfaces.http.config_api import router
from agentos.platform.config.config import Config


@pytest.fixture
def app(tmp_path):
    """构建挂载真实 Config 的测试应用"""
    app = FastAPI()
    app.include_router(router)

    config_path = tmp_path / "config.yml"
    # 写入初始配置
    initial = {
        "llm_providers": {"openai": {"api_key": "sk-xxx"}},
        "agent": {"provider": "openai", "default_model": "gpt-4o-mini"},
        "plugins": {},
    }
    config_path.write_text(yaml.dump(initial), encoding="utf-8")

    cfg = Config(config_path=config_path)
    app.state.config = cfg
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
    assert "llm_providers" in data
    assert "agent" in data
    assert "plugins" in data
    assert data["agent"]["provider"] == "openai"


def test_get_sections_has_defaults(client, app):
    """config.data 中的 section 返回合并后的默认值"""
    resp = client.get("/api/config/sections")
    assert resp.status_code == 200
    data = resp.json()
    # 即使初始 config.yml 中未配 plugins，默认配置会填充
    assert "plugins" in data


# ── 更新 sections ──


def test_update_sections(client, app):
    """正常更新 agent section"""
    resp = client.put("/api/config/sections", json={
        "agent": {"provider": "anthropic", "default_model": "claude-3"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "saved"
    assert "sections" in data
    # 验证 config.yml 被写入
    raw = app.state.config._config_path.read_text(encoding="utf-8")
    written = yaml.safe_load(raw)
    assert written["agent"]["provider"] == "anthropic"


def test_update_sections_multiple(client, app):
    """同时更新多个 section"""
    resp = client.put("/api/config/sections", json={
        "llm_providers": {"anthropic": {"api_key": "sk-yyy"}},
        "plugins": {"search": {"enabled": True}},
    })
    assert resp.status_code == 200
    raw = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    assert "anthropic" in raw["llm_providers"]
    assert raw["plugins"]["search"]["enabled"] is True


def test_update_sections_empty_body(client):
    """未提供任何更新内容时返回 400"""
    resp = client.put("/api/config/sections", json={})
    assert resp.status_code == 400


def test_update_sections_preserves_other_keys(client, app):
    """更新不会覆盖 config.yml 中已有的其他顶层 key"""
    # 先手动添加一个额外 key
    raw = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    raw["custom_key"] = "keep_me"
    app.state.config._config_path.write_text(yaml.dump(raw), encoding="utf-8")

    resp = client.put("/api/config/sections", json={
        "agent": {"provider": "test"},
    })
    assert resp.status_code == 200
    written = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    assert written["custom_key"] == "keep_me"
