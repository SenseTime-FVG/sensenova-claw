"""Tools API 端点单测 — 使用真实组件，无 mock"""
import pytest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sensenova_claw.interfaces.http.tools import router
from sensenova_claw.capabilities.tools.registry import ToolRegistry
from sensenova_claw.platform.config.config import Config


@pytest.fixture
def app(tmp_path):
    """构建挂载真实 ToolRegistry 和 Config 的测试应用"""
    app = FastAPI()
    app.include_router(router)

    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    # 真实 Config
    config_path = tmp_path / "config.yml"
    config_path.write_text("", encoding="utf-8")
    cfg = Config(config_path=config_path)
    cfg.set("system.workspace_dir", str(workspace_dir))

    # 真实 ToolRegistry（自动注册 builtin 工具）
    tool_registry = ToolRegistry()

    app.state.tool_registry = tool_registry
    app.state.config = cfg
    app.state.sensenova_claw_home = str(workspace_dir)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


# ── 列出工具 ──


def test_list_tools(client):
    """正常列出已注册工具"""
    resp = client.get("/api/tools")
    assert resp.status_code == 200
    data = resp.json()
    # 真实 ToolRegistry 注册了多个 builtin 工具
    assert len(data) >= 1
    names = [t["name"] for t in data]
    assert "bash_command" in names
    # 验证字段结构
    bash_tool = [t for t in data if t["name"] == "bash_command"][0]
    assert bash_tool["id"] == "tool-bash_command"
    assert bash_tool["category"] == "builtin"
    assert bash_tool["enabled"] is True
    assert "riskLevel" in bash_tool
    assert "parameters" in bash_tool
    assert "description" in bash_tool


# ── 启用/禁用工具 ──


def test_toggle_tool_disable(client):
    """禁用一个工具"""
    resp = client.put("/api/tools/bash_command/enabled", json={"enabled": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "bash_command"
    assert data["enabled"] is False


def test_toggle_tool_enable(client):
    """启用一个工具"""
    resp = client.put("/api/tools/bash_command/enabled", json={"enabled": True})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True


def test_toggle_tool_not_found(client):
    """工具不存在时返回 404"""
    resp = client.put("/api/tools/nonexistent/enabled", json={"enabled": True})
    assert resp.status_code == 404


def test_list_tools_reflects_prefs(client):
    """先禁用工具再列出，确认 enabled=False 被持久化"""
    # 先禁用
    client.put("/api/tools/bash_command/enabled", json={"enabled": False})
    # 再列出
    resp = client.get("/api/tools")
    data = resp.json()
    bash_tool = [t for t in data if t["name"] == "bash_command"][0]
    assert bash_tool["enabled"] is False
