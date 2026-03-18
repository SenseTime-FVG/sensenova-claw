"""P05: 与 builtin tools 集成"""
import platform
import pytest
from pathlib import Path
from agentos.platform.security.path_policy import PathPolicy, PathVerdict
from agentos.capabilities.tools.builtin import BashCommandTool, ReadFileTool, WriteFileTool

pytestmark = pytest.mark.asyncio


class TestPathPolicyTools:
    async def test_read_in_workspace(self, tmp_workspace):
        (tmp_workspace / "t.md").write_text("hi", encoding="utf-8")
        p = PathPolicy(workspace=tmp_workspace)
        r = await ReadFileTool().execute(file_path=str(tmp_workspace / "t.md"), _path_policy=p)
        assert "hi" in r.get("content", "")

    async def test_write_outside_blocked(self, tmp_workspace, tmp_path):
        p = PathPolicy(workspace=tmp_workspace)
        r = await WriteFileTool().execute(
            file_path=str(tmp_path / "out.md"),
            content="x", _path_policy=p,
        )
        assert r.get("action") == "need_grant"

    async def test_bash_default_cwd(self, tmp_workspace):
        p = PathPolicy(workspace=tmp_workspace)
        cmd = "cd" if platform.system() == "Windows" else "pwd"
        r = await BashCommandTool().execute(command=cmd, _path_policy=p)
        assert r.get("return_code") == 0

    async def test_read_system_denied(self, tmp_workspace):
        p = PathPolicy(workspace=tmp_workspace)
        target = "C:\\Windows\\System32\\config" if platform.system() == "Windows" else "/etc/shadow"
        r = await ReadFileTool().execute(file_path=target, _path_policy=p)
        assert r.get("success") is False

    async def test_write_in_workspace(self, tmp_workspace):
        p = PathPolicy(workspace=tmp_workspace)
        r = await WriteFileTool().execute(
            file_path=str(tmp_workspace / "new.md"),
            content="# New", _path_policy=p,
        )
        assert r.get("success") is True

    async def test_write_system_denied(self, tmp_workspace):
        p = PathPolicy(workspace=tmp_workspace)
        target = "C:\\Windows\\test.txt" if platform.system() == "Windows" else "/etc/test.txt"
        r = await WriteFileTool().execute(file_path=target, content="x", _path_policy=p)
        assert r.get("success") is False

    async def test_read_granted_path(self, tmp_workspace, tmp_path):
        d = tmp_path / "granted"
        d.mkdir()
        (d / "f.txt").write_text("content", encoding="utf-8")
        p = PathPolicy(workspace=tmp_workspace)
        p.grant(str(d))
        r = await ReadFileTool().execute(file_path=str(d / "f.txt"), _path_policy=p)
        assert "content" in r.get("content", "")

    async def test_bash_cwd_outside_blocked(self, tmp_workspace, tmp_path):
        d = tmp_path / "outside"
        d.mkdir()
        p = PathPolicy(workspace=tmp_workspace)
        cmd = "echo hi"
        r = await BashCommandTool().execute(command=cmd, working_dir=str(d), _path_policy=p)
        # 应返回 need_grant 或错误
        assert r.get("action") == "need_grant" or r.get("success") is False


class TestWorkdirRelativePath:
    """相对路径应基于 agent workdir 解析，而非 workspace。"""

    async def test_write_relative_path_uses_workdir(self, tmp_workspace):
        """write_file 使用相对路径时，文件应写入 agent workdir 而非 workspace。"""
        workdir = tmp_workspace / "workdir" / "agent1"
        workdir.mkdir(parents=True)
        p = PathPolicy(workspace=tmp_workspace)
        r = await WriteFileTool().execute(
            file_path="sub/output.txt",
            content="hello",
            _path_policy=p,
            _agent_workdir=str(workdir),
        )
        assert r.get("success") is True
        written = workdir / "sub" / "output.txt"
        assert written.exists()
        assert written.read_text(encoding="utf-8") == "hello"
        # 不应写到 workspace 根目录
        assert not (tmp_workspace / "sub" / "output.txt").exists()

    async def test_read_relative_path_uses_workdir(self, tmp_workspace):
        """read_file 使用相对路径时，应从 agent workdir 读取。"""
        workdir = tmp_workspace / "workdir" / "agent1"
        workdir.mkdir(parents=True)
        (workdir / "data.txt").write_text("workdir content", encoding="utf-8")
        p = PathPolicy(workspace=tmp_workspace)
        r = await ReadFileTool().execute(
            file_path="data.txt",
            _path_policy=p,
            _agent_workdir=str(workdir),
        )
        assert r.get("content") == "workdir content"

    async def test_absolute_path_ignores_workdir(self, tmp_workspace):
        """绝对路径不受 workdir 影响。"""
        workdir = tmp_workspace / "workdir" / "agent1"
        workdir.mkdir(parents=True)
        target = tmp_workspace / "abs.txt"
        target.write_text("absolute", encoding="utf-8")
        p = PathPolicy(workspace=tmp_workspace)
        r = await ReadFileTool().execute(
            file_path=str(target),
            _path_policy=p,
            _agent_workdir=str(workdir),
        )
        assert r.get("content") == "absolute"

    async def test_no_workdir_falls_back(self, tmp_workspace):
        """不传 _agent_workdir 时，相对路径仍可正常工作（回退到当前目录）。"""
        p = PathPolicy(workspace=tmp_workspace)
        r = await WriteFileTool().execute(
            file_path=str(tmp_workspace / "fallback.txt"),
            content="ok",
            _path_policy=p,
        )
        assert r.get("success") is True
