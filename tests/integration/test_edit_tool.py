"""edit_file 工具集成测试"""

import pytest

from sensenova_claw.capabilities.tools.builtin import EditTool

pytestmark = pytest.mark.asyncio


class TestEditTool:
    async def test_edit_replaces_exact_text(self, tmp_workspace):
        target = tmp_workspace / "note.txt"
        target.write_text("hello\nworld\n", encoding="utf-8")

        result = await EditTool().execute(
            path=str(target),
            oldText="world",
            newText="claw",
        )

        assert result["success"] is True
        assert target.read_text(encoding="utf-8") == "hello\nclaw\n"
        assert "Successfully replaced text" in result["message"]
        assert "-world" in result["diff"]
        assert "+claw" in result["diff"]
        assert result["first_changed_line"] == 2

    async def test_edit_fails_when_old_text_missing(self, tmp_workspace):
        target = tmp_workspace / "missing.txt"
        target.write_text("alpha\nbeta\n", encoding="utf-8")

        result = await EditTool().execute(
            path=str(target),
            oldText="gamma",
            newText="delta",
        )

        assert result["success"] is False
        assert "oldText" in result["error"]

    async def test_edit_fails_when_old_text_has_multiple_matches(self, tmp_workspace):
        target = tmp_workspace / "dup.txt"
        target.write_text("same\nsame\n", encoding="utf-8")

        result = await EditTool().execute(
            path=str(target),
            oldText="same",
            newText="once",
        )

        assert result["success"] is False
        assert "multiple" in result["error"]

    async def test_edit_resolves_relative_path_from_agent_workdir(self, tmp_workspace):
        workdir = tmp_workspace / "agent"
        workdir.mkdir()
        target = workdir / "story.txt"
        target.write_text("before after", encoding="utf-8")

        result = await EditTool().execute(
            path="story.txt",
            oldText="before",
            newText="after",
            _agent_workdir=str(workdir),
        )

        assert result["success"] is True
        assert target.read_text(encoding="utf-8") == "after after"

    async def test_edit_recovers_when_post_write_step_fails(self, tmp_workspace, monkeypatch):
        target = tmp_workspace / "recover.txt"
        target.write_text("hello old text", encoding="utf-8")
        tool = EditTool()

        def boom(*args, **kwargs):
            raise RuntimeError("diff failed")

        monkeypatch.setattr(
            "sensenova_claw.capabilities.tools.builtin._generate_unified_diff",
            boom,
        )

        result = await tool.execute(
            path=str(target),
            oldText="old",
            newText="new",
        )

        assert result["success"] is True
        assert "Successfully replaced text" in result["message"]
        assert target.read_text(encoding="utf-8") == "hello new text"
