"""X02: 不同 Agent 的工作目录隔离"""
import pytest
from pathlib import Path
from agentos.capabilities.tools.builtin import ReadFileTool, WriteFileTool

pytestmark = pytest.mark.asyncio


class TestAgentWorkdirIsolation:
    async def test_different_workdirs(self, tmp_path):
        """不同 Agent 通过 _agent_workdir 实现文件隔离"""
        wd1 = tmp_path / "agent1_wd"
        wd1.mkdir()
        wd2 = tmp_path / "agent2_wd"
        wd2.mkdir()
        (wd1 / "a.txt").write_text("agent1 file", encoding="utf-8")
        (wd2 / "b.txt").write_text("agent2 file", encoding="utf-8")

        r = await ReadFileTool().execute(file_path="a.txt", _agent_workdir=str(wd1))
        assert "agent1 file" in r.get("content", "")

        r = await ReadFileTool().execute(file_path="b.txt", _agent_workdir=str(wd2))
        assert "agent2 file" in r.get("content", "")

    async def test_write_isolation(self, tmp_path):
        """不同 Agent 写入各自工作目录"""
        wd1 = tmp_path / "agent1_wd"
        wd1.mkdir()
        wd2 = tmp_path / "agent2_wd"
        wd2.mkdir()

        r1 = await WriteFileTool().execute(
            file_path="out.txt", content="from agent1", _agent_workdir=str(wd1),
        )
        r2 = await WriteFileTool().execute(
            file_path="out.txt", content="from agent2", _agent_workdir=str(wd2),
        )
        assert r1.get("success") is True
        assert r2.get("success") is True
        assert (wd1 / "out.txt").read_text(encoding="utf-8") == "from agent1"
        assert (wd2 / "out.txt").read_text(encoding="utf-8") == "from agent2"
