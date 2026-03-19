"""LLM 状态检测 API 端点单测"""
import pytest
import yaml

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentos.interfaces.http.config_api import router
from agentos.platform.config.config import Config
from agentos.platform.config.llm_presets import LLM_PROVIDER_CATEGORIES


def make_app(tmp_path, config_data: dict) -> FastAPI:
    """构建挂载指定配置的测试应用"""
    app = FastAPI()
    app.include_router(router)

    config_path = tmp_path / "config.yml"
    config_path.write_text(yaml.dump(config_data), encoding="utf-8")

    cfg = Config(config_path=config_path)
    app.state.config = cfg
    return app


# ── /api/config/llm-status ──


def test_llm_status_configured(tmp_path):
    """配置了有效 API key 时 configured=True，providers 包含该提供商"""
    app = make_app(tmp_path, {
        "llm": {
            "providers": {
                "openai": {"api_key": "sk-realkey123"},
            },
        },
    })
    client = TestClient(app)
    resp = client.get("/api/config/llm-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is True
    assert "openai" in data["providers"]


def test_llm_status_not_configured_empty(tmp_path):
    """未配置任何提供商时 configured=False，providers 为空列表"""
    app = make_app(tmp_path, {"llm": {"providers": {}}})
    client = TestClient(app)
    resp = client.get("/api/config/llm-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is False
    assert data["providers"] == []


def test_llm_status_not_configured_placeholder(tmp_path):
    """API key 为未解析的环境变量占位符时 configured=False"""
    app = make_app(tmp_path, {
        "llm": {
            "providers": {
                "openai": {"api_key": "${OPENAI_API_KEY}"},
            },
        },
    })
    client = TestClient(app)
    resp = client.get("/api/config/llm-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is False
    assert data["providers"] == []


def test_llm_status_mock_provider_ignored(tmp_path):
    """mock 提供商不计入 configured"""
    app = make_app(tmp_path, {
        "llm": {
            "providers": {
                "mock": {"api_key": "anything"},
            },
        },
    })
    client = TestClient(app)
    resp = client.get("/api/config/llm-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is False
    assert data["providers"] == []


def test_llm_status_multiple_providers(tmp_path):
    """配置多个有效提供商时全部出现在 providers 中"""
    app = make_app(tmp_path, {
        "llm": {
            "providers": {
                "openai": {"api_key": "sk-aaa"},
                "deepseek": {"api_key": "sk-bbb"},
                "anthropic": {"api_key": "sk-ccc"},
            },
        },
    })
    client = TestClient(app)
    resp = client.get("/api/config/llm-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is True
    assert set(data["providers"]) == {"openai", "deepseek", "anthropic"}


def test_llm_status_no_llm_section(tmp_path):
    """配置中无 llm section 时 configured=False"""
    app = make_app(tmp_path, {"agent": {"model": "gpt-4o-mini"}})
    client = TestClient(app)
    resp = client.get("/api/config/llm-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is False
    assert data["providers"] == []


# ── /api/config/llm-presets ──


def test_llm_presets_returns_categories(tmp_path):
    """llm-presets 端点返回 categories 列表"""
    app = make_app(tmp_path, {})
    client = TestClient(app)
    resp = client.get("/api/config/llm-presets")
    assert resp.status_code == 200
    data = resp.json()
    assert "categories" in data
    assert isinstance(data["categories"], list)
    assert len(data["categories"]) > 0


def test_llm_presets_matches_constant(tmp_path):
    """llm-presets 返回内容与 LLM_PROVIDER_CATEGORIES 完全一致"""
    app = make_app(tmp_path, {})
    client = TestClient(app)
    resp = client.get("/api/config/llm-presets")
    assert resp.status_code == 200
    data = resp.json()
    assert data["categories"] == LLM_PROVIDER_CATEGORIES


def test_llm_presets_structure(tmp_path):
    """每个分类包含 key、label、providers 字段，每个 provider 包含 models"""
    app = make_app(tmp_path, {})
    client = TestClient(app)
    resp = client.get("/api/config/llm-presets")
    assert resp.status_code == 200
    categories = resp.json()["categories"]
    for category in categories:
        assert "key" in category
        assert "label" in category
        assert "providers" in category
        for provider in category["providers"]:
            assert "key" in provider
            assert "label" in provider
            assert "base_url" in provider
            assert "models" in provider
            assert len(provider["models"]) > 0


def test_llm_presets_contains_known_providers(tmp_path):
    """预设中包含 openai、anthropic、gemini 等主要提供商"""
    app = make_app(tmp_path, {})
    client = TestClient(app)
    resp = client.get("/api/config/llm-presets")
    assert resp.status_code == 200
    categories = resp.json()["categories"]
    all_provider_keys = {
        p["key"]
        for cat in categories
        for p in cat["providers"]
    }
    assert "openai" in all_provider_keys
    assert "anthropic" in all_provider_keys
    assert "gemini" in all_provider_keys
