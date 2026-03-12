"""P05: 与 builtin tools 集成"""
import platform
import pytest
from pathlib import Path
from app.security.path_policy import PathPolicy, PathVerdict
from app.tools.builtin import BashCommandTool, ReadFileTool, WriteFileTool

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
