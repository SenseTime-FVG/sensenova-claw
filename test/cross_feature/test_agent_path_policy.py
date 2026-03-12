"""X02: 不同 Agent 的 PathPolicy 隔离"""
import platform
import pytest
from pathlib import Path
from app.security.path_policy import PathPolicy, PathVerdict
from app.agents.config import AgentConfig
from app.tools.builtin import ReadFileTool, WriteFileTool

pytestmark = pytest.mark.asyncio


class TestAgentPathPolicy:
    async def test_different_workspaces(self, tmp_path):
        """不同 Agent 可以有不同的 workspace"""
        ws1 = tmp_path / "agent1_ws"
        ws1.mkdir()
        ws2 = tmp_path / "agent2_ws"
        ws2.mkdir()
        (ws1 / "a.txt").write_text("agent1 file", encoding="utf-8")
        (ws2 / "b.txt").write_text("agent2 file", encoding="utf-8")

        p1 = PathPolicy(workspace=ws1)
        p2 = PathPolicy(workspace=ws2)

        # agent1 可以读自己的文件
        r = await ReadFileTool().execute(file_path=str(ws1 / "a.txt"), _path_policy=p1)
        assert "agent1 file" in r.get("content", "")

        # agent1 不能读 agent2 的文件（不同 workspace）
        r = await ReadFileTool().execute(file_path=str(ws2 / "b.txt"), _path_policy=p1)
        assert r.get("action") == "need_grant" or r.get("success") is False

    async def test_independent_grants(self, tmp_path):
        """grant 在不同 PathPolicy 之间互不影响"""
        ws = tmp_path / "ws"
        ws.mkdir()
        shared = tmp_path / "shared"
        shared.mkdir()

        p1 = PathPolicy(workspace=ws)
        p2 = PathPolicy(workspace=ws)

        p1.grant(str(shared))
        assert p1.check_read(str(shared / "f.txt")) == PathVerdict.ALLOW
        assert p2.check_read(str(shared / "f.txt")) == PathVerdict.NEED_GRANT
