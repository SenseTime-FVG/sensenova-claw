"""Workspace API 端点单测。"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from sensenova_claw.interfaces.http.workspace import router
from sensenova_claw.platform.config.config import Config

pytestmark = pytest.mark.asyncio


@pytest.fixture
def app(tmp_path: Path) -> FastAPI:
    """构建挂载真实 Config 的测试应用。"""
    app = FastAPI()
    app.include_router(router)

    home = tmp_path / "workspace"
    global_dir = home / "agents"
    agent_dir = global_dir / "researcher"
    global_dir.mkdir(parents=True)
    agent_dir.mkdir(parents=True)

    # 全局 workspace 文件
    (global_dir / "AGENTS.md").write_text("# Agents", encoding="utf-8")
    (global_dir / "USER.md").write_text("# User", encoding="utf-8")
    (global_dir / "CUSTOM.md").write_text("# Custom", encoding="utf-8")
    (global_dir / "notes.txt").write_text("not md", encoding="utf-8")

    # per-agent workspace 文件
    (agent_dir / "AGENTS.md").write_text("# Researcher Agents", encoding="utf-8")
    (agent_dir / "PLAN.md").write_text("# Research Plan", encoding="utf-8")

    config_path = tmp_path / "config.yml"
    config_path.write_text("", encoding="utf-8")
    cfg = Config(config_path=config_path)
    cfg.set("system.workspace_dir", str(home))

    app.state.config = cfg
    app.state.sensenova_claw_home = str(home)
    return app


@pytest.fixture
async def client(app: FastAPI):
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_list_workspace_files(client: AsyncClient):
    """默认列出全局 agents/ 下的 .md 文件。"""
    resp = await client.get("/api/workspace/files")
    assert resp.status_code == 200

    data = resp.json()
    names = [f["name"] for f in data]
    assert names == ["AGENTS.md", "CUSTOM.md", "USER.md"]
    assert "notes.txt" not in names
    for f in data:
        assert "size" in f
        assert f["editable"] is True


async def test_list_workspace_files_for_agent(client: AsyncClient):
    """传入 agent_id 时应读取对应 agent 目录。"""
    resp = await client.get("/api/workspace/files", params={"agent_id": "researcher"})
    assert resp.status_code == 200

    names = [f["name"] for f in resp.json()]
    assert names == ["AGENTS.md", "PLAN.md"]


async def test_list_workspace_files_global_alias(client: AsyncClient):
    """agent_id=_global 时仍应读取全局目录。"""
    resp = await client.get("/api/workspace/files", params={"agent_id": "_global"})
    assert resp.status_code == 200

    names = [f["name"] for f in resp.json()]
    assert names == ["AGENTS.md", "CUSTOM.md", "USER.md"]


async def test_list_workspace_files_dir_not_exists(client: AsyncClient, app: FastAPI):
    """workspace 根目录不存在时返回空列表。"""
    app.state.sensenova_claw_home = "/nonexistent/path"

    resp = await client.get("/api/workspace/files")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_read_file(client: AsyncClient):
    """正常读取全局 .md 文件。"""
    resp = await client.get("/api/workspace/files/AGENTS.md")
    assert resp.status_code == 200

    data = resp.json()
    assert data["name"] == "AGENTS.md"
    assert data["content"] == "# Agents"


async def test_read_agent_file(client: AsyncClient):
    """正常读取 per-agent .md 文件。"""
    resp = await client.get("/api/workspace/files/PLAN.md", params={"agent_id": "researcher"})
    assert resp.status_code == 200

    data = resp.json()
    assert data["name"] == "PLAN.md"
    assert data["content"] == "# Research Plan"


async def test_read_file_not_md(client: AsyncClient):
    """非 .md 文件拒绝访问。"""
    resp = await client.get("/api/workspace/files/notes.txt")
    assert resp.status_code == 400


async def test_read_file_not_found(client: AsyncClient):
    """读取不存在的文件返回 404。"""
    resp = await client.get("/api/workspace/files/MISSING.md")
    assert resp.status_code == 404


async def test_reject_path_traversal_agent_id(client: AsyncClient):
    """非法 agent_id 不应跳出 agents 根目录。"""
    resp = await client.get("/api/workspace/files", params={"agent_id": ".."})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "非法 agent_id"


async def test_write_file(client: AsyncClient, app: FastAPI):
    """正常写入全局文件。"""
    resp = await client.put("/api/workspace/files/NEW.md", json={"content": "# New"})
    assert resp.status_code == 200

    data = resp.json()
    assert data["name"] == "NEW.md"
    assert data["status"] == "saved"
    assert (Path(app.state.sensenova_claw_home) / "agents" / "NEW.md").read_text(encoding="utf-8") == "# New"


async def test_write_file_for_agent(client: AsyncClient, app: FastAPI):
    """正常写入 per-agent 文件。"""
    resp = await client.put(
        "/api/workspace/files/NOTES.md",
        params={"agent_id": "researcher"},
        json={"content": "# Agent Notes"},
    )
    assert resp.status_code == 200

    assert (
        Path(app.state.sensenova_claw_home) / "agents" / "researcher" / "NOTES.md"
    ).read_text(encoding="utf-8") == "# Agent Notes"


async def test_write_file_not_md(client: AsyncClient):
    """非 .md 文件拒绝写入。"""
    resp = await client.put("/api/workspace/files/bad.txt", json={"content": "x"})
    assert resp.status_code == 400


async def test_delete_file(client: AsyncClient, app: FastAPI):
    """正常删除全局用户自建文件。"""
    resp = await client.delete("/api/workspace/files/CUSTOM.md")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"
    assert not (Path(app.state.sensenova_claw_home) / "agents" / "CUSTOM.md").exists()


async def test_delete_file_for_agent(client: AsyncClient, app: FastAPI):
    """正常删除 per-agent 用户自建文件。"""
    resp = await client.delete("/api/workspace/files/PLAN.md", params={"agent_id": "researcher"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"
    assert not (Path(app.state.sensenova_claw_home) / "agents" / "researcher" / "PLAN.md").exists()


async def test_delete_core_file_agents(client: AsyncClient):
    """核心文件 AGENTS.md 不允许删除。"""
    resp = await client.delete("/api/workspace/files/AGENTS.md")
    assert resp.status_code == 403


async def test_delete_core_file_user(client: AsyncClient):
    """核心文件 USER.md 不允许删除。"""
    resp = await client.delete("/api/workspace/files/USER.md")
    assert resp.status_code == 403


async def test_delete_file_not_found(client: AsyncClient):
    """删除不存在的文件返回 404。"""
    resp = await client.delete("/api/workspace/files/NOPE.md")
    assert resp.status_code == 404


async def test_delete_file_not_md(client: AsyncClient):
    """非 .md 文件拒绝删除。"""
    resp = await client.delete("/api/workspace/files/bad.txt")
    assert resp.status_code == 400
