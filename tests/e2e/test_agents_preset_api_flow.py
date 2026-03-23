"""Agents API e2e：preset 保留 ID 与运行态覆盖层链路。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from agentos.adapters.storage.repository import Repository
from agentos.capabilities.agents.registry import AgentRegistry
from agentos.capabilities.skills.registry import SkillRegistry
from agentos.capabilities.tools.registry import ToolRegistry
from agentos.interfaces.http.agents import router
from agentos.platform.config.config import Config
from agentos.platform.config.config_manager import ConfigManager
from agentos.platform.secrets.store import InMemorySecretStore
from agentos.kernel.events.bus import PublicEventBus


async def _build_app(tmp_path: Path) -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    agentos_home = tmp_path / ".agentos_home"
    agent_config_dir = agentos_home / "agents"
    agent_config_dir.mkdir(parents=True)
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    config_path = tmp_path / "config.yml"
    config_path.write_text(yaml.dump({
        "agents": {
            "preset-agent": {
                "name": "Preset Agent",
                "model": "gpt-4o-mini",
            },
        },
    }), encoding="utf-8")
    secret_store = InMemorySecretStore()
    cfg = Config(config_path=config_path, secret_store=secret_store)
    cfg.set("system.workspace_dir", str(workspace_dir))
    bus = PublicEventBus()
    config_manager = ConfigManager(config=cfg, event_bus=bus, secret_store=secret_store)

    agent_registry = AgentRegistry(agentos_home=agentos_home)
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
    app.state.config_manager = config_manager
    app.state.agentos_home = str(agentos_home)
    return app


@pytest.mark.asyncio
async def test_agents_preset_api_flow_e2e(tmp_path):
    """完整链路：创建冲突 -> 更新落盘 -> 自定义 agent CRUD 持久化 -> 删除生效。"""
    app = await _build_app(tmp_path)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1) preset 同名创建冲突
        resp = await client.post("/api/agents", json={"id": "preset-agent", "name": "dup"})
        assert resp.status_code == 409

        # 2) preset 可更新，写入 config.yml + SYSTEM_PROMPT.md
        resp = await client.put(
            "/api/agents/preset-agent/config",
            json={
                "name": "Preset Agent Updated",
                "temperature": 0.55,
                "systemPrompt": "你是预置 Agent",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Preset Agent Updated"

        written = yaml.safe_load((tmp_path / "config.yml").read_text(encoding="utf-8"))
        assert written["agents"]["preset-agent"]["name"] == "Preset Agent Updated"
        assert written["agents"]["preset-agent"]["temperature"] == 0.55
        prompt_file = tmp_path / ".agentos_home" / "agents" / "preset-agent" / "SYSTEM_PROMPT.md"
        assert prompt_file.exists()
        assert prompt_file.read_text(encoding="utf-8") == "你是预置 Agent"

        # 3) 非 preset agent 可创建，且持久化到 config.yml
        resp = await client.post("/api/agents", json={
            "id": "custom-agent",
            "name": "Custom Agent",
            "system_prompt": "你是自定义 Agent",
        })
        assert resp.status_code == 200
        written = yaml.safe_load((tmp_path / "config.yml").read_text(encoding="utf-8"))
        assert written["agents"]["custom-agent"]["name"] == "Custom Agent"

        # 4) 删除后从 config.yml 中移除
        resp = await client.delete("/api/agents/custom-agent")
        assert resp.status_code == 200
        written = yaml.safe_load((tmp_path / "config.yml").read_text(encoding="utf-8"))
        assert "custom-agent" not in written["agents"]
