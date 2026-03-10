"""workspace/manager 单元测试

测试 ensure_workspace() 和 load_workspace_files()。
"""

from __future__ import annotations

import pytest

from app.workspace.manager import ensure_workspace, load_workspace_files


@pytest.mark.asyncio
async def test_ensure_workspace_creates_dir_and_files(tmp_path):
    """确保 workspace 目录和默认文件被创建"""
    workspace_dir = str(tmp_path / "workspace")
    await ensure_workspace(workspace_dir)

    agents_md = tmp_path / "workspace" / "AGENTS.md"
    user_md = tmp_path / "workspace" / "USER.md"

    assert agents_md.exists()
    assert user_md.exists()
    assert len(agents_md.read_text(encoding="utf-8")) > 0
    assert len(user_md.read_text(encoding="utf-8")) > 0


@pytest.mark.asyncio
async def test_ensure_workspace_does_not_overwrite(tmp_path):
    """已有文件不会被覆盖"""
    workspace_dir = str(tmp_path / "workspace")
    (tmp_path / "workspace").mkdir()
    custom_content = "# Custom AGENTS.md"
    (tmp_path / "workspace" / "AGENTS.md").write_text(custom_content, encoding="utf-8")

    await ensure_workspace(workspace_dir)

    agents_md = tmp_path / "workspace" / "AGENTS.md"
    assert agents_md.read_text(encoding="utf-8") == custom_content


@pytest.mark.asyncio
async def test_load_workspace_files(tmp_path):
    """加载 workspace 文件"""
    workspace_dir = str(tmp_path / "workspace")
    await ensure_workspace(workspace_dir)

    files = await load_workspace_files(workspace_dir)

    assert len(files) == 2
    names = {f.name for f in files}
    assert "AGENTS.md" in names
    assert "USER.md" in names
    for f in files:
        assert len(f.content) > 0


@pytest.mark.asyncio
async def test_load_workspace_files_empty_file_skipped(tmp_path):
    """空文件被跳过"""
    workspace_dir = str(tmp_path / "workspace")
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace" / "AGENTS.md").write_text("Agent content", encoding="utf-8")
    (tmp_path / "workspace" / "USER.md").write_text("", encoding="utf-8")

    files = await load_workspace_files(workspace_dir)

    assert len(files) == 1
    assert files[0].name == "AGENTS.md"


@pytest.mark.asyncio
async def test_load_workspace_files_missing_dir(tmp_path):
    """目录不存在时返回空列表"""
    workspace_dir = str(tmp_path / "nonexistent")
    files = await load_workspace_files(workspace_dir)
    assert files == []


@pytest.mark.asyncio
async def test_load_workspace_files_whitespace_only_skipped(tmp_path):
    """只有空白的文件被跳过"""
    workspace_dir = str(tmp_path / "workspace")
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace" / "AGENTS.md").write_text("  \n  \n  ", encoding="utf-8")
    (tmp_path / "workspace" / "USER.md").write_text("Real content", encoding="utf-8")

    files = await load_workspace_files(workspace_dir)

    assert len(files) == 1
    assert files[0].name == "USER.md"
