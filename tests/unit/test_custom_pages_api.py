"""custom_pages / mini-app API 单测。"""

from __future__ import annotations
from dataclasses import dataclass
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sensenova_claw.capabilities.agents.registry import AgentRegistry
from sensenova_claw.interfaces.http.custom_pages import router
from sensenova_claw.platform.config.config import Config


class DummyGateway:
    def __init__(self) -> None:
        self.created_sessions: list[dict] = []
        self.user_inputs: list[dict] = []

    async def create_session(self, agent_id: str = "default", meta: dict | None = None, channel_id: str = "") -> dict:
        session_id = f"sess_{len(self.created_sessions) + 1}"
        self.created_sessions.append(
            {
                "agent_id": agent_id,
                "meta": meta or {},
                "channel_id": channel_id,
                "session_id": session_id,
            }
        )
        return {"session_id": session_id, "created_at": 0}

    async def send_user_input(
        self,
        session_id: str,
        content: str,
        attachments: list | None = None,
        context_files: list | None = None,
        source: str = "websocket",
    ) -> str:
        turn_id = f"turn_{len(self.user_inputs) + 1}"
        self.user_inputs.append(
            {
                "session_id": session_id,
                "content": content,
                "attachments": attachments or [],
                "context_files": context_files or [],
                "source": source,
                "turn_id": turn_id,
            }
        )
        return turn_id


@pytest.fixture
def app(tmp_path: Path) -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    sensenova_claw_home = tmp_path / "sensenova_claw_home"
    sensenova_claw_home.mkdir()
    previous_home = os.environ.get("SENSENOVA_CLAW_HOME")
    os.environ["SENSENOVA_CLAW_HOME"] = str(sensenova_claw_home)
    cfg = Config(config_path=tmp_path / "config.yml")

    agent_registry = AgentRegistry(sensenova_claw_home=sensenova_claw_home)
    agent_registry.load_from_config(cfg.data)

    gateway = DummyGateway()

    @dataclass
    class Services:
        gateway: DummyGateway

    app.state.sensenova_claw_home = str(sensenova_claw_home)
    app.state.config = cfg
    app.state.agent_registry = agent_registry
    app.state.services = Services(gateway=gateway)
    yield app
    if previous_home is None:
        os.environ.pop("SENSENOVA_CLAW_HOME", None)
    else:
        os.environ["SENSENOVA_CLAW_HOME"] = previous_home


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    with TestClient(app) as client:
        yield client


def test_create_miniapp_page_creates_workspace_and_agent(app: FastAPI, client: TestClient) -> None:
    resp = client.post(
        "/api/custom-pages",
        json={
            "name": "研究工作台",
            "description": "为研究任务生成可复用的工作区页面",
            "icon": "BookOpen",
            "agent_id": "default",
            "create_dedicated_agent": True,
            "workspace_mode": "scratch",
            "builder_type": "builtin",
            "generation_prompt": "做一个可复用页面壳体的研究工作区，只在必要时让 Agent 更新内容",
            "templates": [
                {"title": "整理资料", "desc": "先汇总现有资料并建立任务卡片"},
                {"title": "提炼结论", "desc": "根据结果更新下一步计划"},
            ],
        },
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["type"] == "miniapp"
    assert data["build_status"] == "ready"
    assert data["agent_id"].startswith("miniapp-")
    assert data["preview_mode"] == "server"
    assert data["entry_file_path"].endswith("/app/index.html")
    assert data["server_entry_file_path"].endswith("/server.py")

    agent = app.state.agent_registry.get(data["agent_id"])
    assert agent is not None
    assert agent.workdir.endswith(f"/workdir/{data['workspace_root']}")

    home = Path(app.state.sensenova_claw_home)
    index_path = home / "workdir" / data["entry_file_path"]
    bridge_path = home / "workdir" / data["bridge_script_path"]
    server_path = home / "workdir" / data["server_entry_file_path"]
    state_path = home / "workdir" / data["workspace_root"] / "data" / "workspace_state.json"
    prompt_path = home / "agents" / data["agent_id"] / "SYSTEM_PROMPT.md"

    assert index_path.exists()
    assert bridge_path.exists()
    assert server_path.exists()
    assert state_path.exists()
    assert prompt_path.exists()
    assert "Standalone Workspace Server" in index_path.read_text(encoding="utf-8")
    assert "window.SensenovaClawMiniApp" in bridge_path.read_text(encoding="utf-8")
    assert '"/api/workspace-state"' in server_path.read_text(encoding="utf-8")
    assert "自包含的 client-server 系统" in prompt_path.read_text(encoding="utf-8")


def test_reuse_project_preserves_license(app: FastAPI, client: TestClient, tmp_path: Path) -> None:
    source_project = tmp_path / "sample_project"
    source_project.mkdir()
    (source_project / "index.html").write_text(
        "<!doctype html><html><body><h1>Sample</h1></body></html>",
        encoding="utf-8",
    )
    (source_project / "LICENSE").write_text("MIT License", encoding="utf-8")

    resp = client.post(
        "/api/custom-pages",
        json={
            "name": "复用项目",
            "description": "复用现有 HTML 项目",
            "icon": "Code",
            "agent_id": "default",
            "create_dedicated_agent": False,
            "workspace_mode": "reuse",
            "source_project_path": str(source_project),
            "builder_type": "builtin",
            "generation_prompt": "复用这个项目并接入 Sensenova-Claw",
        },
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["agent_id"] == "default"
    assert data["preserved_license_files"]

    home = Path(app.state.sensenova_claw_home)
    entry = home / "workdir" / data["entry_file_path"]
    attributions = home / "workdir" / data["app_dir"] / "ATTRIBUTIONS.md"
    copied_license = home / "workdir" / data["preserved_license_files"][0]

    assert entry.exists()
    assert attributions.exists()
    assert copied_license.exists()
    assert "sensenova_claw-bridge.js" in entry.read_text(encoding="utf-8")
    assert "MIT License" in copied_license.read_text(encoding="utf-8")


def test_interaction_endpoint_creates_and_reuses_session(app: FastAPI, client: TestClient) -> None:
    create_resp = client.post(
        "/api/custom-pages",
        json={
            "name": "工作台助手",
            "description": "一个通用工作台",
            "agent_id": "default",
            "create_dedicated_agent": False,
            "workspace_mode": "scratch",
            "builder_type": "builtin",
            "generation_prompt": "做一个可以和 Agent 协作的工作台页面",
        },
    )
    page = create_resp.json()

    first = client.post(
        f"/api/custom-pages/{page['slug']}/interactions",
        json={
            "action": "task_card_clicked",
            "payload": {"title": "整理需求"},
        },
    )
    assert first.status_code == 200
    first_data = first.json()
    assert first_data["session_id"] == "sess_1"
    assert first_data["turn_id"] == "turn_1"

    second = client.post(
        f"/api/custom-pages/{page['slug']}/interactions",
        json={
            "action": "freeform_note_submitted",
            "payload": {"note": "请继续优化页面"},
        },
    )
    assert second.status_code == 200
    second_data = second.json()
    assert second_data["session_id"] == "sess_1"
    assert second_data["turn_id"] == "turn_2"
    assert second_data["should_refresh_workspace"] is False

    gateway: DummyGateway = app.state.services.gateway
    assert len(gateway.created_sessions) == 1
    assert len(gateway.user_inputs) == 2
    assert "MiniApp 交互事件" in gateway.user_inputs[0]["content"]
    assert "整理需求" in gateway.user_inputs[0]["content"]


def test_actions_endpoint_server_target_logs_without_agent_session(app: FastAPI, client: TestClient) -> None:
    create_resp = client.post(
        "/api/custom-pages",
        json={
            "name": "服务端工作台",
            "description": "一个把部分动作交给服务端处理的工作区",
            "agent_id": "default",
            "create_dedicated_agent": False,
            "workspace_mode": "scratch",
            "builder_type": "builtin",
            "generation_prompt": "做一个通用工作台，允许部分动作只发给服务端",
        },
    )
    page = create_resp.json()

    resp = client.post(
        f"/api/custom-pages/{page['slug']}/actions",
        json={
            "target": "server",
            "action": "save_workspace_snapshot",
            "payload": {"cards": 3, "summary": "保存当前状态"},
        },
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["ok"] is True
    assert data["target"] == "server"
    assert data["session_id"] == ""
    assert data["turn_id"] == ""

    gateway: DummyGateway = app.state.services.gateway
    assert gateway.created_sessions == []
    assert gateway.user_inputs == []

    home = Path(app.state.sensenova_claw_home)
    log_path = home / "workdir" / page["workspace_root"] / "interaction_log.jsonl"
    assert log_path.exists()
    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines
    last = lines[-1]
    assert "save_workspace_snapshot" in last
    assert '"target": "server"' in last
    assert '"refresh_mode": "none"' in last


def test_actions_endpoint_immediate_refresh_flag_is_explicit(app: FastAPI, client: TestClient) -> None:
    create_resp = client.post(
        "/api/custom-pages",
        json={
            "name": "重建工作台",
            "description": "一个需要显式触发重刷的工作区",
            "agent_id": "default",
            "create_dedicated_agent": False,
            "workspace_mode": "scratch",
            "builder_type": "builtin",
            "generation_prompt": "做一个自带 server 的 workspace，普通问答不刷新，只有显式要求时才立即刷新",
        },
    )
    page = create_resp.json()

    resp = client.post(
        f"/api/custom-pages/{page['slug']}/actions",
        json={
            "target": "agent",
            "action": "request_workspace_rebuild",
            "payload": {"reason": "schema changed"},
            "refresh_mode": "immediate",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["target"] == "agent"
    assert data["should_refresh_workspace"] is True
    assert data["refresh_mode"] == "immediate"


def test_preview_endpoint_proxies_standalone_workspace_server(app: FastAPI, client: TestClient) -> None:
    create_resp = client.post(
        "/api/custom-pages",
        json={
            "name": "预览工作台",
            "description": "验证独立 workspace server 预览",
            "agent_id": "default",
            "create_dedicated_agent": False,
            "workspace_mode": "scratch",
            "builder_type": "builtin",
            "generation_prompt": "做一个自带 server 的 workspace，并通过独立 web server 提供页面和状态 API",
        },
    )
    page = create_resp.json()

    preview_resp = client.get(f"/api/custom-pages/{page['slug']}/preview/")
    assert preview_resp.status_code == 200
    assert "Standalone Workspace Server" in preview_resp.text

    state_resp = client.get(f"/api/custom-pages/{page['slug']}/preview/api/workspace-state")
    assert state_resp.status_code == 200
    state = state_resp.json()
    assert state["workspace_slug"] == page["slug"]
    assert isinstance(state["prepared_units"], list)
