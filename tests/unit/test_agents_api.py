"""Agents API 端点单测（使用 TestClient + mock app.state）"""
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentos.interfaces.http.agents import router
from agentos.capabilities.agents.config import AgentConfig


def _make_agent_config(id="default", name="Default Agent", enabled=True, **kwargs):
    """辅助：创建 AgentConfig 实例"""
    return AgentConfig(
        id=id,
        name=name,
        enabled=enabled,
        provider=kwargs.get("provider", "openai"),
        model=kwargs.get("model", "gpt-4o-mini"),
        temperature=kwargs.get("temperature", 0.2),
        max_tokens=kwargs.get("max_tokens"),
        system_prompt=kwargs.get("system_prompt", ""),
        tools=kwargs.get("tools", []),
        skills=kwargs.get("skills", []),
        can_delegate_to=kwargs.get("can_delegate_to", []),
        max_delegation_depth=kwargs.get("max_delegation_depth", 3),
        created_at=kwargs.get("created_at", 1000.0),
        updated_at=kwargs.get("updated_at", 1000.0),
    )


@pytest.fixture
def app(tmp_path):
    app = FastAPI()
    app.include_router(router)

    default_agent = _make_agent_config()
    custom_agent = _make_agent_config(id="research", name="Research Agent")

    # mock agent_registry
    agent_registry = MagicMock()
    agent_registry.list_all.return_value = [default_agent, custom_agent]
    agent_registry.get.side_effect = lambda aid: {
        "default": default_agent,
        "research": custom_agent,
    }.get(aid)
    agent_registry.register.return_value = None
    agent_registry.save.return_value = None
    agent_registry.update.side_effect = lambda aid, updates: _make_agent_config(id=aid, **updates)
    agent_registry.delete.side_effect = lambda aid: aid != "nonexistent"

    # mock tool_registry
    mock_tool = MagicMock()
    mock_tool.description = "Run bash"
    mock_tool.risk_level = MagicMock(value="high")
    mock_tool.parameters = {}

    tool_registry = MagicMock()
    tool_registry._tools = {"bash_command": mock_tool}
    tool_registry.get.side_effect = lambda name: mock_tool if name == "bash_command" else None

    # mock skill_registry
    mock_skill = MagicMock()
    mock_skill.name = "test-skill"
    mock_skill.description = "A test skill"
    mock_skill.install_info = None
    mock_skill.path = Path("/fake/builtin/path")

    skill_registry = MagicMock()
    skill_registry.get_all.return_value = [mock_skill]

    # mock config (workspace_dir 指向 tmp_path)
    config = MagicMock()
    config.get.return_value = str(tmp_path / "workspace")

    # mock services (with repo)
    repo = AsyncMock()
    repo.list_sessions.return_value = [
        {"session_id": "s1", "agent_id": "default", "last_active": 0, "status": "active",
         "channel": "websocket", "message_count": 5, "created_at": 0},
    ]
    services = MagicMock()
    services.repo = repo

    app.state.agent_registry = agent_registry
    app.state.tool_registry = tool_registry
    app.state.skill_registry = skill_registry
    app.state.config = config
    app.state.services = services

    return app


@pytest.fixture
def client(app):
    return TestClient(app)


# ── 列表 ──


def test_list_agents(client):
    """正常列出所有 Agent"""
    resp = client.get("/api/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    # 每个 agent 包含基本字段
    assert data[0]["id"] == "default"
    assert "toolCount" in data[0]
    assert "sessionCount" in data[0]
    assert "lastActive" in data[0]


def test_list_agents_no_sessions(client, app):
    """Agent 无会话时 lastActive 应为 'never'"""
    app.state.services.repo.list_sessions.return_value = []
    resp = client.get("/api/agents")
    assert resp.status_code == 200
    for agent in resp.json():
        assert agent["lastActive"] == "never"


# ── 详情 ──


def test_get_agent_found(client):
    """正常获取 Agent 详情"""
    resp = client.get("/api/agents/default")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "default"
    assert "sessions" in data
    assert "toolsDetail" in data
    assert "skillsDetail" in data


def test_get_agent_not_found(client, app):
    """查询不存在的 Agent 返回 404"""
    resp = client.get("/api/agents/nonexistent")
    assert resp.status_code == 404


# ── 创建 ──


def test_create_agent(client, app):
    """正常创建 Agent"""
    # 确保 registry.get 对新 id 返回 None（不存在）
    original = app.state.agent_registry.get.side_effect

    def get_side(aid):
        if aid == "new-agent":
            return None
        return original(aid)

    app.state.agent_registry.get.side_effect = get_side

    resp = client.post("/api/agents", json={
        "id": "new-agent",
        "name": "New Agent",
        "description": "A new agent",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "new-agent"
    app.state.agent_registry.register.assert_called_once()
    app.state.agent_registry.save.assert_called_once()


def test_create_agent_conflict(client):
    """创建已存在的 Agent 返回 409"""
    resp = client.post("/api/agents", json={
        "id": "default",
        "name": "Dup Agent",
    })
    assert resp.status_code == 409


# ── 更新配置 ──


def test_update_agent_config(client):
    """正常更新 Agent 配置"""
    resp = client.put("/api/agents/default/config", json={
        "name": "Updated",
        "temperature": 0.5,
    })
    assert resp.status_code == 200
    app_state = client.app.state
    app_state.agent_registry.update.assert_called_once()


def test_update_agent_config_syncs_global_for_default(client, app):
    """更新 default Agent 时同步全局 config"""
    resp = client.put("/api/agents/default/config", json={
        "provider": "anthropic",
        "model": "claude-3",
    })
    assert resp.status_code == 200
    app.state.config.set.assert_any_call("agent.provider", "anthropic")
    app.state.config.set.assert_any_call("agent.default_model", "claude-3")


def test_update_agent_config_not_found(client, app):
    """更新不存在的 Agent 返回 404"""
    resp = client.put("/api/agents/nonexistent/config", json={"name": "x"})
    assert resp.status_code == 404


# ── 删除 ──


def test_delete_agent(client):
    """正常删除非 default Agent"""
    resp = client.delete("/api/agents/research")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


def test_delete_default_agent(client):
    """不允许删除 default Agent"""
    resp = client.delete("/api/agents/default")
    assert resp.status_code == 400


def test_delete_agent_not_found(client):
    """删除不存在的 Agent 返回 404"""
    resp = client.delete("/api/agents/nonexistent")
    assert resp.status_code == 404


# ── 偏好设置 ──


def test_update_preferences(client):
    """正常更新偏好"""
    resp = client.put("/api/agents/default/preferences", json={
        "tools": {"bash_command": False},
        "skills": {"test-skill": True},
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "saved"


def test_update_preferences_agent_not_found(client, app):
    """偏好更新：Agent 不存在返回 404"""
    resp = client.put("/api/agents/nonexistent/preferences", json={
        "tools": {"bash_command": False},
    })
    assert resp.status_code == 404
