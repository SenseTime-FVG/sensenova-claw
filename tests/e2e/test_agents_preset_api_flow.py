"""Agents API e2e：preset 保留 ID 与运行态覆盖层链路。"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from agentos.adapters.storage.repository import Repository
from agentos.capabilities.agents.registry import AgentRegistry
from agentos.capabilities.skills.registry import SkillRegistry
from agentos.capabilities.tools.registry import ToolRegistry
from agentos.interfaces.http.agents import router
from agentos.platform.config.config import Config


async def _build_app(tmp_path: Path) -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    agentos_home = tmp_path / ".agentos_home"
    agent_config_dir = agentos_home / "agents"
    agent_config_dir.mkdir(parents=True)
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    config_path = tmp_path / "config.yml"
    config_path.write_text("", encoding="utf-8")
    cfg = Config(config_path=config_path)
    cfg.set("system.workspace_dir", str(workspace_dir))

    agent_registry = AgentRegistry()
    # 通过 config 加载预置 agent
    cfg.data.setdefault("agents", {})["preset-agent"] = {
        "name": "Preset Agent",
        "model": "gpt-4o-mini",
    }
    agent_registry.load_from_config(cfg.data)

    db_path = Path("/tmp") / f"agentos_agents_e2e_{uuid.uuid4().hex}.db"
    repo = Repository(db_path=str(db_path))
    await repo.init()

    tool_registry = ToolRegistry()
    skills_dir = workspace_dir / "skills"
    skills_dir.mkdir()
    skill_registry = SkillRegistry(
        workspace_dir=skills_dir,
        state_file=workspace_dir / "skills_state.json",
        builtin_dir=None,
    )
    skill_registry.load_skills(cfg.data)

    @dataclass
    class Services:
        repo: Repository

    app.state.services = Services(repo=repo)
    app.state.agent_registry = agent_registry
    app.state.tool_registry = tool_registry
    app.state.skill_registry = skill_registry
    app.state.config = cfg
    app.state.agentos_home = str(agentos_home)
    return app


@pytest.mark.asyncio
async def test_agents_preset_api_flow_e2e(tmp_path):
    """完整链路：创建冲突 -> 删除拦截 -> 更新落盘 -> 自定义 agent CRUD 回归。"""
    app = await _build_app(tmp_path)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1) preset 同名创建冲突
        resp = await client.post("/api/agents", json={"id": "preset-agent", "name": "dup"})
        assert resp.status_code == 409

        # 2) preset 不允许删除
        resp = await client.delete("/api/agents/preset-agent")
        assert resp.status_code == 400

        # 3) preset 可更新，写入 AGENTOS_HOME 覆盖层
        resp = await client.put(
            "/api/agents/preset-agent/config",
            json={"name": "Preset Agent Updated", "temperature": 0.55},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Preset Agent Updated"

        persisted = tmp_path / ".agentos_home" / "agents" / "preset-agent" / "config.json"
        assert persisted.exists()
        stored = json.loads(persisted.read_text(encoding="utf-8"))
        assert stored["name"] == "Preset Agent Updated"

        # 4) 非 preset agent 仍可创建和删除
        resp = await client.post("/api/agents", json={"id": "custom-agent", "name": "Custom Agent"})
        assert resp.status_code == 200
        resp = await client.delete("/api/agents/custom-agent")
        assert resp.status_code == 200
