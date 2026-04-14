"""Office API 单测。"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sensenova_claw.adapters.storage.repository import Repository
from sensenova_claw.capabilities.agents.registry import AgentRegistry
from sensenova_claw.interfaces.http.office_api import router
from sensenova_claw.platform.config.config import Config
from sensenova_claw.platform.secrets.store import InMemorySecretStore


@pytest.fixture
def app(tmp_path):
    app = FastAPI()
    app.include_router(router)

    config_path = tmp_path / "config.yml"
    config_path.write_text(yaml.dump({
        "agents": {
            "ppt-agent": {"name": "PPT 生成助手", "model": "gpt-4o-mini"},
            "data-analyst": {"name": "数据分析助手", "model": "gpt-4o-mini"},
        },
    }), encoding="utf-8")
    cfg = Config(config_path=config_path, secret_store=InMemorySecretStore())

    agent_registry = AgentRegistry(sensenova_claw_home=tmp_path / ".sensenova-claw")
    agent_registry.load_from_config(cfg.data)

    repo = Repository(db_path=str(tmp_path / "test.db"))
    asyncio.run(repo.init())

    @dataclass
    class Services:
        repo: Repository

    app.state.services = Services(repo=repo)
    app.state.agent_registry = agent_registry
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_office_agent_status_defaults_to_idle_for_all_agents(client: TestClient):
    resp = client.get("/api/office/agent-status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["agents"]["default"]["status"] == "idle"
    assert data["agents"]["ppt-agent"]["status"] == "idle"
    assert data["agents"]["data-analyst"]["status"] == "idle"


def test_office_agent_status_marks_started_turn_agent_as_running(client: TestClient, app: FastAPI):
    asyncio.run(app.state.services.repo.create_session("sess-running", meta={"agent_id": "ppt-agent"}))
    asyncio.run(app.state.services.repo.create_turn("turn-running", "sess-running", "生成周报"))
    asyncio.run(app.state.services.repo.create_session("sess-idle", meta={"agent_id": "data-analyst"}))
    asyncio.run(app.state.services.repo.create_turn("turn-idle", "sess-idle", "分析数据"))
    asyncio.run(app.state.services.repo.complete_turn("turn-idle", "已完成"))

    resp = client.get("/api/office/agent-status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["agents"]["ppt-agent"]["status"] == "running"
    assert data["agents"]["data-analyst"]["status"] == "idle"
