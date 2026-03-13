"""T06: 工具执行 + 结果截断"""
import pytest
from agentos.capabilities.tools.builtin import ReadFileTool, WriteFileTool, BashCommandTool

pytestmark = pytest.mark.asyncio


class TestToolExecution:
    async def test_read_file(self, tmp_workspace):
        (tmp_workspace / "test.md").write_text("hello world", encoding="utf-8")
        tool = ReadFileTool()
        result = await tool.execute(file_path=str(tmp_workspace / "test.md"))
        assert "hello world" in result.get("content", "")

    async def test_read_file_not_found(self, tmp_workspace):
        tool = ReadFileTool()
        result = await tool.execute(file_path=str(tmp_workspace / "nope.md"))
        assert result.get("success") is False

    async def test_write_file(self, tmp_workspace):
        tool = WriteFileTool()
        result = await tool.execute(
            file_path=str(tmp_workspace / "out.md"),
            content="# Output",
        )
        assert result["success"] is True
        assert (tmp_workspace / "out.md").read_text(encoding="utf-8") == "# Output"

    async def test_write_file_append(self, tmp_workspace):
        f = tmp_workspace / "app.md"
        f.write_text("line1\n", encoding="utf-8")
        tool = WriteFileTool()
        await tool.execute(file_path=str(f), content="line2\n", mode="append")
        assert "line1" in f.read_text(encoding="utf-8")
        assert "line2" in f.read_text(encoding="utf-8")

    async def test_bash_command(self, tmp_workspace):
        import platform
        tool = BashCommandTool()
        cmd = "echo hello" if platform.system() != "Windows" else "echo hello"
        result = await tool.execute(command=cmd)
        assert result["return_code"] == 0
        assert "hello" in result["stdout"]

    async def test_read_with_line_range(self, tmp_workspace):
        f = tmp_workspace / "lines.txt"
        f.write_text("\n".join(f"line{i}" for i in range(10)), encoding="utf-8")
        tool = ReadFileTool()
        result = await tool.execute(file_path=str(f), start_line=3, num_lines=2)
        content = result["content"]
        assert "line2" in content
        assert "line3" in content
        assert "line0" not in content
