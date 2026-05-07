"""apply_patch 工具集成测试"""

from __future__ import annotations

import pytest

from sensenova_claw.capabilities.tools.builtin import ApplyPatchTool
from sensenova_claw.platform.security.path_policy import PathPolicy

pytestmark = pytest.mark.asyncio


class TestApplyPatchTool:
    async def test_add_update_delete_and_move_files(self, tmp_workspace):
        src = tmp_workspace / "src.txt"
        src.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

        patch = """*** Begin Patch
*** Add File: created.txt
+hello
+world
*** Update File: src.txt
@@
 alpha
-beta
+beta2
 gamma
*** Update File: created.txt
*** Move to: moved.txt
@@
 hello
 world
+done
*** Delete File: src.txt
*** End Patch"""

        result = await ApplyPatchTool().execute(
            input=patch,
            _agent_workdir=str(tmp_workspace),
        )

        assert result["success"] is True
        assert (tmp_workspace / "src.txt").exists() is False
        assert (tmp_workspace / "created.txt").exists() is False
        assert (tmp_workspace / "moved.txt").read_text(encoding="utf-8") == "hello\nworld\ndone\n"
        assert (tmp_workspace / "summary") is not None
        assert result["summary"]["added"] == ["created.txt"]
        assert result["summary"]["modified"] == ["src.txt", "moved.txt"]
        assert result["summary"]["deleted"] == ["src.txt"]

    async def test_resolves_relative_paths_from_agent_workdir(self, tmp_workspace):
        workdir = tmp_workspace / "agent"
        workdir.mkdir()
        (workdir / "note.txt").write_text("before\nmiddle\nafter\n", encoding="utf-8")

        patch = """*** Begin Patch
*** Update File: note.txt
@@
 before
-middle
+changed
 after
*** End Patch"""

        result = await ApplyPatchTool().execute(
            input=patch,
            _agent_workdir=str(workdir),
        )

        assert result["success"] is True
        assert (workdir / "note.txt").read_text(encoding="utf-8") == "before\nchanged\nafter\n"
        assert result["summary"]["modified"] == ["note.txt"]

    async def test_rejects_invalid_patch_boundary(self, tmp_workspace):
        result = await ApplyPatchTool().execute(
            input="*** Begin Patch\n*** Add File: bad.txt\n+oops\n",
            _agent_workdir=str(tmp_workspace),
        )

        assert result["success"] is False
        assert "End Patch" in result["error"]

    async def test_respects_injected_path_policy(self, tmp_workspace, tmp_path):
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        policy = PathPolicy(workspace=tmp_workspace)

        result = await ApplyPatchTool().execute(
            input="*** Begin Patch\n*** Add File: blocked.txt\n+secret\n*** End Patch",
            _agent_workdir=str(outside_dir),
            _path_policy=policy,
        )

        assert result["success"] is False
        assert "未授权" in result["error"]

    async def test_reports_valid_hunk_headers_for_invalid_header(self, tmp_workspace):
        result = await ApplyPatchTool().execute(
            input="*** Begin Patch\nFile: bad.txt\n*** End Patch",
            _agent_workdir=str(tmp_workspace),
        )

        assert result["success"] is False
        assert result["error"] == (
            "Invalid patch hunk at line 2: 'File: bad.txt' is not a valid hunk header. "
            "Valid hunk headers: '*** Add File: {path}', '*** Delete File: {path}', "
            "'*** Update File: {path}'"
        )

    async def test_reports_missing_context_marker_after_first_chunk(self, tmp_workspace):
        target = tmp_workspace / "multi.txt"
        target.write_text("line1\nline2\nline3\n", encoding="utf-8")

        patch = """*** Begin Patch
*** Update File: multi.txt
@@
 line1
-line2
+line2b
 line3
tail
*** End Patch"""

        result = await ApplyPatchTool().execute(
            input=patch,
            _agent_workdir=str(tmp_workspace),
        )

        assert result["success"] is False
        assert result["error"] == (
            "Invalid patch hunk at line 8: Expected update hunk to start with a @@ "
            "context marker, got: 'tail'"
        )

    async def test_reports_unexpected_line_in_update_hunk(self, tmp_workspace):
        target = tmp_workspace / "bad.txt"
        target.write_text("alpha\n", encoding="utf-8")

        patch = """*** Begin Patch
*** Update File: bad.txt
@@
oops
*** End Patch"""

        result = await ApplyPatchTool().execute(
            input=patch,
            _agent_workdir=str(tmp_workspace),
        )

        assert result["success"] is False
        assert result["error"] == (
            "Invalid patch hunk at line 4: Unexpected line found in update hunk: 'oops'. "
            "Every line should start with ' ' (context line), '+' (added line), or '-' "
            "(removed line)"
        )

    async def test_accepts_heredoc_wrapped_patch_boundaries(self, tmp_workspace):
        result = await ApplyPatchTool().execute(
            input="<<EOF\n*** Begin Patch\n*** Add File: ok.txt\n+ok\n*** End Patch\nEOF",
            _agent_workdir=str(tmp_workspace),
        )

        assert result["success"] is True
        assert (tmp_workspace / "ok.txt").read_text(encoding="utf-8") == "ok\n"
