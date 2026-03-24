"""Workspace API 端点单测 — 使用真实组件，无 mock"""
import pytest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sensenova_claw.interfaces.http.workspace import router
from sensenova_claw.platform.config.config import Config


@pytest.fixture
def app(tmp_path):
    """构建挂载真实 Config 的测试应用"""
    app = FastAPI()
    app.include_router(router)

    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()

    # 预创建一些文件
    (ws_dir / "AGENTS.md").write_text("# Agents", encoding="utf-8")
    (ws_dir / "USER.md").write_text("# User", encoding="utf-8")
    (ws_dir / "CUSTOM.md").write_text("# Custom", encoding="utf-8")
    (ws_dir / "notes.txt").write_text("not md")  # 非 .md 文件

    # 真实 Config
    config_path = tmp_path / "config.yml"
    config_path.write_text("", encoding="utf-8")
    cfg = Config(config_path=config_path)
    cfg.set("system.workspace_dir", str(ws_dir))

    app.state.config = cfg
    app.state.sensenova_claw_home = str(ws_dir)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


# ── 列出文件 ──


def test_list_workspace_files(client):
    """正常列出 workspace 下的 .md 文件"""
    resp = client.get("/api/workspace/files")
    assert resp.status_code == 200
    data = resp.json()
    names = [f["name"] for f in data]
    assert "AGENTS.md" in names
    assert "USER.md" in names
    assert "CUSTOM.md" in names
    # 非 .md 文件不应出现
    assert "notes.txt" not in names
    # 每个文件有 size 和 editable
    for f in data:
        assert "size" in f
        assert f["editable"] is True


def test_list_workspace_files_dir_not_exists(client, app):
    """workspace 目录不存在时返回空列表"""
    app.state.sensenova_claw_home = "/nonexistent/path"
    resp = client.get("/api/workspace/files")
    assert resp.status_code == 200
    assert resp.json() == []


# ── 读取文件 ──


def test_read_file(client):
    """正常读取 .md 文件"""
    resp = client.get("/api/workspace/files/AGENTS.md")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "AGENTS.md"
    assert data["content"] == "# Agents"


def test_read_file_not_md(client):
    """非 .md 文件拒绝访问"""
    resp = client.get("/api/workspace/files/notes.txt")
    assert resp.status_code == 400


def test_read_file_not_found(client):
    """读取不存在的文件返回 404"""
    resp = client.get("/api/workspace/files/MISSING.md")
    assert resp.status_code == 404


# ── 写入文件 ──


def test_write_file(client):
    """正常写入/更新文件"""
    resp = client.put("/api/workspace/files/NEW.md", json={"content": "# New"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "NEW.md"
    assert data["status"] == "saved"
    assert data["size"] > 0


def test_write_file_not_md(client):
    """非 .md 文件拒绝写入"""
    resp = client.put("/api/workspace/files/bad.txt", json={"content": "x"})
    assert resp.status_code == 400


# ── 删除文件 ──


def test_delete_file(client):
    """正常删除用户自建文件"""
    resp = client.delete("/api/workspace/files/CUSTOM.md")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


def test_delete_core_file_agents(client):
    """核心文件 AGENTS.md 不允许删除"""
    resp = client.delete("/api/workspace/files/AGENTS.md")
    assert resp.status_code == 403


def test_delete_core_file_user(client):
    """核心文件 USER.md 不允许删除"""
    resp = client.delete("/api/workspace/files/USER.md")
    assert resp.status_code == 403


def test_delete_file_not_found(client):
    """删除不存在的文件返回 404"""
    resp = client.delete("/api/workspace/files/NOPE.md")
    assert resp.status_code == 404


def test_delete_file_not_md(client):
    """非 .md 文件拒绝删除"""
    resp = client.delete("/api/workspace/files/bad.txt")
    assert resp.status_code == 400
