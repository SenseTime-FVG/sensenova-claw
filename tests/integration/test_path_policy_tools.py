"""P05: 与 builtin tools 集成"""
import platform
import pytest
from pathlib import Path
from sensenova_claw.capabilities.tools.builtin import BashCommandTool, ReadFileTool, WriteFileTool

pytestmark = pytest.mark.asyncio


class TestBuiltinTools:
    async def test_read_in_workspace(self, tmp_workspace):
        (tmp_workspace / "t.md").write_text("hi", encoding="utf-8")
        r = await ReadFileTool().execute(file_path=str(tmp_workspace / "t.md"))
        assert "hi" in r.get("content", "")

    async def test_write_anywhere(self, tmp_workspace, tmp_path):
        r = await WriteFileTool().execute(
            file_path=str(tmp_path / "out.md"),
            content="x",
        )
        assert r.get("success") is True

    async def test_bash_default_cwd(self, tmp_workspace):
        cmd = "cd" if platform.system() == "Windows" else "pwd"
        r = await BashCommandTool().execute(command=cmd)
        assert r.get("return_code") == 0

    async def test_bash_with_workdir(self, tmp_workspace):
        cmd = "cd" if platform.system() == "Windows" else "pwd"
        r = await BashCommandTool().execute(command=cmd, _agent_workdir=str(tmp_workspace))
        assert r.get("return_code") == 0

    async def test_read_nonexistent(self, tmp_workspace):
        r = await ReadFileTool().execute(file_path=str(tmp_workspace / "missing.txt"))
        assert r.get("success") is False

    async def test_write_in_workspace(self, tmp_workspace):
        r = await WriteFileTool().execute(
            file_path=str(tmp_workspace / "new.md"),
            content="# New",
        )
        assert r.get("success") is True

    async def test_read_with_workdir(self, tmp_workspace):
        d = tmp_workspace / "granted"
        d.mkdir()
        (d / "f.txt").write_text("content", encoding="utf-8")
        r = await ReadFileTool().execute(file_path="f.txt", _agent_workdir=str(d))
        assert "content" in r.get("content", "")


class TestWorkdirRelativePath:
    """相对路径应基于 agent workdir 解析。"""

    async def test_write_relative_path_uses_workdir(self, tmp_workspace):
        """write_file 使用相对路径时，文件应写入 agent workdir。"""
        workdir = tmp_workspace / "workdir" / "agent1"
        workdir.mkdir(parents=True)
        r = await WriteFileTool().execute(
            file_path="sub/output.txt",
            content="hello",
            _agent_workdir=str(workdir),
        )
        assert r.get("success") is True
        written = workdir / "sub" / "output.txt"
        assert written.exists()
        assert written.read_text(encoding="utf-8") == "hello"
        assert not (tmp_workspace / "sub" / "output.txt").exists()

    async def test_read_relative_path_uses_workdir(self, tmp_workspace):
        """read_file 使用相对路径时，应从 agent workdir 读取。"""
        workdir = tmp_workspace / "workdir" / "agent1"
        workdir.mkdir(parents=True)
        (workdir / "data.txt").write_text("workdir content", encoding="utf-8")
        r = await ReadFileTool().execute(
            file_path="data.txt",
            _agent_workdir=str(workdir),
        )
        assert r.get("content") == "workdir content"

    async def test_absolute_path_ignores_workdir(self, tmp_workspace):
        """绝对路径不受 workdir 影响。"""
        workdir = tmp_workspace / "workdir" / "agent1"
        workdir.mkdir(parents=True)
        target = tmp_workspace / "abs.txt"
        target.write_text("absolute", encoding="utf-8")
        r = await ReadFileTool().execute(
            file_path=str(target),
            _agent_workdir=str(workdir),
        )
        assert r.get("content") == "absolute"

    async def test_no_workdir_falls_back(self, tmp_workspace):
        """不传 _agent_workdir 时，绝对路径仍可正常工作。"""
        r = await WriteFileTool().execute(
            file_path=str(tmp_workspace / "fallback.txt"),
            content="ok",
        )
        assert r.get("success") is True
