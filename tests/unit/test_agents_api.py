"""Agents API 端点单测 — 使用真实组件，无 mock"""
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sensenova_claw.capabilities.tools.base import Tool
from sensenova_claw.interfaces.http.agents import router
from sensenova_claw.capabilities.agents.registry import AgentRegistry
from sensenova_claw.capabilities.tools.registry import ToolRegistry
from sensenova_claw.capabilities.skills.registry import SkillRegistry
from sensenova_claw.platform.config.config import Config
from sensenova_claw.platform.config.config_manager import ConfigManager
from sensenova_claw.platform.secrets.store import InMemorySecretStore
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.adapters.storage.repository import Repository
from sensenova_claw.capabilities.mcp.runtime import SessionMcpRuntime


class _SendMessageTool(Tool):
    name = "send_message"
    description = "向其他 Agent 发送消息"
    parameters = {"type": "object", "properties": {}}


def _write_probe_server(tmp_path: Path) -> Path:
    script_path = tmp_path / "mcp_probe_server.py"
    script_path.write_text(
        """
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("probe")

@mcp.tool()
def search_docs(query: str) -> str:
    return f"DOCS:{query}"

@mcp.tool()
def fetch_page(path: str) -> str:
    return f"PAGE:{path}"

if __name__ == "__main__":
    mcp.run("stdio")
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return script_path


@pytest.fixture
def app(tmp_path):
    """构建挂载真实组件的 FastAPI 测试应用"""
    app = FastAPI()
    app.include_router(router)

    # 临时 workspace
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    # 真实 Config
    config_path = tmp_path / "config.yml"
    probe_server = _write_probe_server(tmp_path)
    config_path.write_text(yaml.dump({
        "mcp": {
            "servers": {
                "docs-search": {
                    "transport": "stdio",
                    "command": sys.executable,
                    "args": [str(probe_server)],
                    "timeout": 5,
                },
            },
        },
        "agents": {
            "research": {
                "name": "Research Agent",
                "model": "gpt-4o-mini",
            },
        },
    }), encoding="utf-8")
    secret_store = InMemorySecretStore()
    cfg = Config(config_path=config_path, secret_store=secret_store)
    cfg.set("system.workspace_dir", str(workspace_dir))
    bus = PublicEventBus()
    config_manager = ConfigManager(config=cfg, event_bus=bus, secret_store=secret_store)

    # 真实 AgentRegistry，加载 default agent
    agent_config_dir = tmp_path / "agents"
    agent_config_dir.mkdir()
    agent_registry = AgentRegistry(sensenova_claw_home=tmp_path / ".sensenova-claw")
    agent_registry.load_from_config(cfg.data)

    # 真实 ToolRegistry（自动注册 builtin 工具）
    tool_registry = ToolRegistry()

    # 真实 SkillRegistry（不加载 builtin skills 目录，避免环境依赖）
    skills_dir = workspace_dir / "skills"
    skills_dir.mkdir()
    sample_skill_dir = skills_dir / "sample-skill"
    sample_skill_dir.mkdir()
    (sample_skill_dir / "SKILL.md").write_text(
        "---\nname: sample-skill\ndescription: 示例技能\n---\n测试 skill\n",
        encoding="utf-8",
    )
    state_file = workspace_dir / "skills_state.json"
    skill_registry = SkillRegistry(
        workspace_dir=skills_dir,
        state_file=state_file,
        builtin_dir=None,
    )
    skill_registry.load_skills(cfg.data)

    # 真实 Repository（临时 SQLite）
    repo = Repository(db_path=str(tmp_path / "test.db"))
    asyncio.run(repo.init())

    @dataclass
    class Services:
        repo: Repository
    services = Services(repo=repo)

    app.state.agent_registry = agent_registry
    app.state.tool_registry = tool_registry
    app.state.skill_registry = skill_registry
    app.state.config = cfg
    app.state.config_manager = config_manager
    app.state.services = services
    app.state.sensenova_claw_home = str(tmp_path / ".sensenova-claw")

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
    ids = {a["id"] for a in data}
    assert "default" in ids
    assert "research" in ids
    # 每个 agent 包含基本字段
    for agent in data:
        assert "toolCount" in agent
        assert "sessionCount" in agent
        assert "lastActive" in agent
        assert "mcpServersDetail" not in agent
        assert "mcpToolsDetail" not in agent


def test_list_agents_no_sessions(client):
    """Agent 无会话时 lastActive 应为 'never'"""
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
    assert "mcpServersDetail" in data
    assert "mcpToolsDetail" in data


def test_get_agent_includes_mcp_details(client):
    """Agent 详情应返回 MCP server/tool 明细和启用状态。"""
    resp = client.get("/api/agents/default")
    assert resp.status_code == 200
    data = resp.json()

    server = next(item for item in data["mcpServersDetail"] if item["name"] == "docs-search")
    assert server["enabled"] is True
    assert server["toolCount"] == 2

    tool_names = {item["name"] for item in data["mcpToolsDetail"]}
    assert "docs-search/search_docs" in tool_names
    assert "docs-search/fetch_page" in tool_names


def test_get_agent_reuses_cached_mcp_catalog(client, monkeypatch):
    """同一配置下重复打开 Agent 详情时，不应重复探测 MCP catalog。"""
    original = SessionMcpRuntime._list_tools_for_server
    calls = {"count": 0}

    async def counted(self, server_cfg):  # type: ignore[no-untyped-def]
        calls["count"] += 1
        return await original(self, server_cfg)

    monkeypatch.setattr(SessionMcpRuntime, "_list_tools_for_server", counted)

    first = client.get("/api/agents/default")
    second = client.get("/api/agents/default")

    assert first.status_code == 200
    assert second.status_code == 200
    assert calls["count"] == 1


def test_get_agent_not_found(client):
    """查询不存在的 Agent 返回 404"""
    resp = client.get("/api/agents/nonexistent")
    assert resp.status_code == 404


# ── 创建 ──


def test_create_agent(client):
    """正常创建 Agent"""
    resp = client.post("/api/agents", json={
        "id": "new-agent",
        "name": "New Agent",
        "description": "A new agent",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "new-agent"


def test_create_agent_persists_to_config_and_survives_reload(client, app):
    """创建 Agent 后应写回 config.yml，重载注册表后仍能读取。"""
    resp = client.post("/api/agents", json={
        "id": "persisted-agent",
        "name": "Persisted Agent",
        "description": "persist me",
        "model": "gpt-4o-mini",
        "temperature": 0.4,
        "system_prompt": "你是持久化测试助手",
    })
    assert resp.status_code == 200

    written = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    assert written["agents"]["persisted-agent"]["name"] == "Persisted Agent"
    assert written["agents"]["persisted-agent"]["model"] == "gpt-4o-mini"
    assert written["agents"]["persisted-agent"]["temperature"] == 0.4
    assert "system_prompt" not in written["agents"]["persisted-agent"]

    prompt_file = Path(app.state.sensenova_claw_home) / "agents" / "persisted-agent" / "SYSTEM_PROMPT.md"
    assert prompt_file.exists()
    assert prompt_file.read_text(encoding="utf-8") == "你是持久化测试助手"

    reloaded = AgentRegistry(sensenova_claw_home=Path(app.state.sensenova_claw_home))
    reloaded.load_from_config(app.state.config._load_config())
    persisted = reloaded.get("persisted-agent")
    assert persisted is not None
    assert persisted.name == "Persisted Agent"
    assert persisted.system_prompt == "你是持久化测试助手"


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
    data = resp.json()
    assert data["name"] == "Updated"
    assert data["temperature"] == 0.5


def test_update_agent_config_persists_to_config(client, app):
    """更新 Agent 配置后应写回 config.yml 与 SYSTEM_PROMPT.md。"""
    resp = client.put("/api/agents/default/config", json={
        "name": "Updated Default",
        "model": "claude-opus",
        "temperature": 0.6,
        "systemPrompt": "新的系统提示词",
    })
    assert resp.status_code == 200

    written = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    assert written["agents"]["default"]["name"] == "Updated Default"
    assert written["agents"]["default"]["model"] == "claude-opus"
    assert written["agents"]["default"]["temperature"] == 0.6

    prompt_file = Path(app.state.sensenova_claw_home) / "agents" / "default" / "SYSTEM_PROMPT.md"
    assert prompt_file.exists()
    assert prompt_file.read_text(encoding="utf-8") == "新的系统提示词"


def test_update_agent_config_persists_mcp_whitelists(client, app):
    """更新 Agent MCP 白名单后应写回 config.yml 并反映到详情接口。"""
    resp = client.put("/api/agents/default/config", json={
        "mcp_servers": ["docs-search"],
        "mcp_tools": ["docs-search/search_docs"],
    })
    assert resp.status_code == 200

    data = resp.json()
    server = next(item for item in data["mcpServersDetail"] if item["name"] == "docs-search")
    assert server["enabled"] is True
    search_tool = next(item for item in data["mcpToolsDetail"] if item["name"] == "docs-search/search_docs")
    fetch_tool = next(item for item in data["mcpToolsDetail"] if item["name"] == "docs-search/fetch_page")
    assert search_tool["enabled"] is True
    assert fetch_tool["enabled"] is False

    written = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    assert written["agents"]["default"]["mcp_servers"] == ["docs-search"]
    assert written["agents"]["default"]["mcp_tools"] == ["docs-search/search_docs"]


def test_update_agent_config_can_disable_delegation(client, app):
    """显式传 null 时，应禁用委托并隐藏 send_message。"""
    app.state.tool_registry.register(_SendMessageTool())

    resp = client.put("/api/agents/default/config", json={
        "can_delegate_to": None,
    })
    assert resp.status_code == 200

    data = resp.json()
    assert data["canDelegateTo"] is None
    assert "send_message" not in data["tools"]

    written = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    assert written["agents"]["default"]["can_delegate_to"] is None


def test_update_agent_config_model(client):
    """更新 default Agent 的 model"""
    resp = client.put("/api/agents/default/config", json={
        "model": "claude-opus",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["model"] == "claude-opus"


def test_update_agent_config_not_found(client):
    """更新不存在的 Agent 返回 404"""
    resp = client.put("/api/agents/nonexistent/config", json={"name": "x"})
    assert resp.status_code == 404


# ── 删除 ──


def test_delete_agent(client):
    """正常删除非 default Agent"""
    resp = client.delete("/api/agents/research")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


def test_delete_agent_persists_to_config(client, app):
    """删除 Agent 后应同步从 config.yml 中移除。"""
    resp = client.delete("/api/agents/research")
    assert resp.status_code == 200

    written = yaml.safe_load(app.state.config._config_path.read_text(encoding="utf-8"))
    assert "research" not in written.get("agents", {})


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
        "skills": {"sample-skill": False},
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "saved"

    prefs = json.loads((Path(client.app.state.sensenova_claw_home) / ".agent_preferences.json").read_text(encoding="utf-8"))
    assert prefs["skills"]["sample-skill"] is False

    default_detail = client.get("/api/agents/default").json()
    default_skill = next(skill for skill in default_detail["skillsDetail"] if skill["name"] == "sample-skill")
    assert default_skill["enabled"] is False

    research_detail = client.get("/api/agents/research").json()
    research_skill = next(skill for skill in research_detail["skillsDetail"] if skill["name"] == "sample-skill")
    assert research_skill["enabled"] is False


def test_update_preferences_agent_not_found(client):
    """偏好更新：Agent 不存在返回 404"""
    resp = client.put("/api/agents/nonexistent/preferences", json={
        "tools": {"bash_command": False},
    })
    assert resp.status_code == 404
