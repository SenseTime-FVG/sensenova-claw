"""Skills API 端点单测 — 使用真实组件，无 mock
市场相关接口（market_service）设为 None 并跳过测试。
"""
import asyncio
import pytest
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentos.interfaces.http.skills import router, invoke_router
from agentos.capabilities.skills.registry import Skill, SkillRegistry
from agentos.platform.config.config import Config
from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.runtime.publisher import EventPublisher


def _create_test_skill(skill_dir: Path, name: str = "test-skill",
                       description: str = "Test skill",
                       body: str = "Do $ARGUMENTS") -> Path:
    """在指定目录下创建一个合法的 SKILL.md 文件"""
    skill_path = skill_dir / name
    skill_path.mkdir(parents=True, exist_ok=True)
    skill_md = skill_path / "SKILL.md"
    content = f"""---
name: {name}
description: {description}
---
{body}
"""
    skill_md.write_text(content, encoding="utf-8")
    return skill_path


@pytest.fixture
def app(tmp_path):
    """构建挂载真实组件的测试应用"""
    app = FastAPI()
    app.include_router(router)
    app.include_router(invoke_router)

    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    # 真实 Config
    config_path = tmp_path / "config.yml"
    config_path.write_text("", encoding="utf-8")
    cfg = Config(config_path=config_path)
    cfg.set("system.workspace_dir", str(workspace_dir))

    # 真实 SkillRegistry
    skills_dir = workspace_dir / "skills"
    skills_dir.mkdir()
    state_file = workspace_dir / "skills_state.json"

    # 创建一个测试 skill
    _create_test_skill(skills_dir, "test-skill", "Test skill", "Do $ARGUMENTS")

    skill_registry = SkillRegistry(
        workspace_dir=skills_dir,
        state_file=state_file,
        builtin_dir=None,
    )
    skill_registry.load_skills(cfg.data)

    # 真实 EventPublisher（用于 invoke_skill）
    bus = PublicEventBus()
    publisher = EventPublisher(bus)

    @dataclass
    class Services:
        publisher: EventPublisher
    services = Services(publisher=publisher)

    app.state.skill_registry = skill_registry
    app.state.config = cfg
    app.state.market_service = None  # 无市场 key，跳过市场测试
    app.state.services = services

    return app


@pytest.fixture
def client(app):
    return TestClient(app)


# ── 本地 skill 列表 ──


def test_list_skills(client):
    """正常列出本地已加载的 skills"""
    resp = client.get("/api/skills")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    skill = [s for s in data if s["name"] == "test-skill"][0]
    assert "source" in skill
    assert "enabled" in skill
    assert skill["enabled"] is True


# ── 启用/禁用 ──


def test_toggle_enabled(client):
    """禁用后再启用 skill"""
    resp = client.patch("/api/skills/test-skill", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    # 禁用后列表中不应出现
    resp = client.get("/api/skills")
    names = [s["name"] for s in resp.json()]
    assert "test-skill" not in names

    # 重新启用
    resp = client.patch("/api/skills/test-skill", json={"enabled": True})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True


# ── 斜杠命令调用 ──


def test_invoke_skill(client):
    """正常调用 skill（通过斜杠命令）"""
    resp = client.post(
        "/api/sessions/sess_123/skill-invoke",
        json={"skill_name": "test-skill", "arguments": "hello"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["skill_name"] == "test-skill"


def test_invoke_skill_not_found(client):
    """调用不存在的 skill 返回 404"""
    resp = client.post(
        "/api/sessions/sess_123/skill-invoke",
        json={"skill_name": "nonexistent", "arguments": ""},
    )
    assert resp.status_code == 404


# ── 市场相关接口（需要 market_service，跳过） ──


@pytest.mark.skip(reason="需要 market_service（ClawHub/Anthropic API key）")
def test_market_search(client):
    resp = client.get("/api/skills/market/search?source=clawhub&q=test")
    assert resp.status_code == 200


@pytest.mark.skip(reason="需要 market_service（ClawHub/Anthropic API key）")
def test_install(client):
    resp = client.post("/api/skills/install", json={"source": "clawhub", "id": "x"})
    assert resp.status_code == 200


@pytest.mark.skip(reason="需要 market_service（ClawHub/Anthropic API key）")
def test_uninstall(client):
    resp = client.delete("/api/skills/test-skill")
    assert resp.status_code == 200


@pytest.mark.skip(reason="需要 market_service（ClawHub/Anthropic API key）")
def test_check_updates(client):
    resp = client.post("/api/skills/check-updates")
    assert resp.status_code == 200


@pytest.mark.skip(reason="需要 market_service（ClawHub/Anthropic API key）")
def test_update_skill(client):
    resp = client.post("/api/skills/test-skill/update")
    assert resp.status_code == 200


@pytest.mark.skip(reason="需要 market_service（ClawHub/Anthropic API key）")
def test_market_detail(client):
    resp = client.get("/api/skills/market/detail?source=clawhub&id=x")
    assert resp.status_code == 200
