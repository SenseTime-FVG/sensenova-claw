"""Tools API 端点单测（使用 TestClient + mock app.state）"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentos.interfaces.http.tools import router


@pytest.fixture
def app(tmp_path):
    app = FastAPI()
    app.include_router(router)

    # mock tool
    mock_tool = MagicMock()
    mock_tool.description = "Execute bash commands"
    mock_tool.risk_level = MagicMock(value="high")
    mock_tool.parameters = {"command": {"type": "string"}}

    tool_registry = MagicMock()
    tool_registry._tools = {"bash_command": mock_tool}
    tool_registry.get.side_effect = lambda name: mock_tool if name == "bash_command" else None

    # config (workspace_dir 指向 tmp_path，避免写到真实文件系统)
    config = MagicMock()
    config.get.return_value = str(tmp_path / "workspace")

    app.state.tool_registry = tool_registry
    app.state.config = config

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
    assert len(data) == 1
    tool = data[0]
    assert tool["name"] == "bash_command"
    assert tool["id"] == "tool-bash_command"
    assert tool["description"] == "Execute bash commands"
    assert tool["category"] == "builtin"
    assert tool["enabled"] is True
    assert tool["riskLevel"] == "high"
    assert "parameters" in tool


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
    assert data[0]["enabled"] is False
