"""workspace 管理单元测试

测试 AGENTOS_HOME 目录管理：ensure_agentos_home()、ensure_agent_workspace()、
load_workspace_files()、resolve_agent_workdir()、resolve_agentos_home()。
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from agentos.platform.config.workspace import (
    ensure_agent_workspace,
    ensure_agentos_home,
    ensure_workspace,
    load_workspace_files,
    resolve_agent_workdir,
    resolve_agentos_home,
)


# ── ensure_workspace（向后兼容）──────────────────────


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


# ── ensure_agentos_home ──────────────────────────────


@pytest.mark.asyncio
async def test_ensure_agentos_home_creates_structure(tmp_path):
    """创建完整的 AGENTOS_HOME 目录结构"""
    home = tmp_path / ".agentos"
    await ensure_agentos_home(home)

    assert (home / "agents" / "default").is_dir()
    assert (home / "data").is_dir()
    assert (home / "skills").is_dir()
    assert (home / "workdir" / "default").is_dir()
    assert (home / "agents" / "default" / "AGENTS.md").exists()
    assert (home / "agents" / "default" / "USER.md").exists()


@pytest.mark.asyncio
async def test_ensure_agentos_home_copies_builtin(tmp_path):
    """从代码仓库 .agentos/ 复制内置资源"""
    home = tmp_path / "home"
    project = tmp_path / "project"

    # 模拟代码仓库中的 .agentos/
    builtin_agent = project / ".agentos" / "agents" / "default"
    builtin_agent.mkdir(parents=True)
    (builtin_agent / "AGENTS.md").write_text("# Builtin Agent", encoding="utf-8")

    await ensure_agentos_home(home, project_root=project)

    # 应该从 builtin 复制
    assert (home / "agents" / "default" / "AGENTS.md").read_text(encoding="utf-8") == "# Builtin Agent"


@pytest.mark.asyncio
async def test_ensure_agentos_home_no_overwrite(tmp_path):
    """已有文件不被覆盖"""
    home = tmp_path / ".agentos"
    agent_dir = home / "agents" / "default"
    agent_dir.mkdir(parents=True)
    (agent_dir / "AGENTS.md").write_text("# Custom", encoding="utf-8")

    await ensure_agentos_home(home)

    assert (agent_dir / "AGENTS.md").read_text(encoding="utf-8") == "# Custom"
    # USER.md 缺失应被创建
    assert (agent_dir / "USER.md").exists()


# ── resolve_agentos_home ──────────────────────────────


def test_resolve_agentos_home_default():
    """默认返回 ~/.agentos"""
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("AGENTOS_HOME", None)
        result = resolve_agentos_home(None)
        assert result == Path.home() / ".agentos"


def test_resolve_agentos_home_from_env(tmp_path):
    """环境变量 AGENTOS_HOME 覆盖默认值"""
    custom = str(tmp_path / "custom_home")
    with patch.dict(os.environ, {"AGENTOS_HOME": custom}):
        result = resolve_agentos_home(None)
        assert str(result) == str(Path(custom).resolve())


# ── ensure_agent_workspace ──────────────────────────


@pytest.mark.asyncio
async def test_ensure_agent_workspace_creates_agent_dir(tmp_path):
    """为指定 agent 创建独立目录和文件"""
    home = str(tmp_path / ".agentos")
    await ensure_agentos_home(Path(home))

    await ensure_agent_workspace(home, "researcher")

    agent_dir = tmp_path / ".agentos" / "agents" / "researcher"
    assert (agent_dir / "AGENTS.md").exists()
    assert (agent_dir / "USER.md").exists()
    # workdir 也应被创建
    assert (tmp_path / ".agentos" / "workdir" / "researcher").is_dir()


@pytest.mark.asyncio
async def test_ensure_agent_workspace_copies_from_default(tmp_path):
    """agent 的文件从 default agent 模板复制"""
    home = str(tmp_path / ".agentos")
    await ensure_agentos_home(Path(home))

    # 修改 default 模板
    (tmp_path / ".agentos" / "agents" / "default" / "AGENTS.md").write_text(
        "# Custom Default", encoding="utf-8"
    )

    await ensure_agent_workspace(home, "researcher")

    agent_md = tmp_path / ".agentos" / "agents" / "researcher" / "AGENTS.md"
    assert agent_md.read_text(encoding="utf-8") == "# Custom Default"


@pytest.mark.asyncio
async def test_ensure_agent_workspace_no_overwrite(tmp_path):
    """已有的 agent 文件不被覆盖"""
    home = str(tmp_path / ".agentos")
    await ensure_agentos_home(Path(home))

    agent_dir = tmp_path / ".agentos" / "agents" / "researcher"
    agent_dir.mkdir(parents=True)
    (agent_dir / "AGENTS.md").write_text("# My Custom", encoding="utf-8")

    await ensure_agent_workspace(home, "researcher")

    assert (agent_dir / "AGENTS.md").read_text(encoding="utf-8") == "# My Custom"
    assert (agent_dir / "USER.md").exists()


# ── load_workspace_files ──────────────────────────────


@pytest.mark.asyncio
async def test_load_workspace_files_per_agent(tmp_path):
    """按 agent_id 从对应目录加载文件"""
    home = str(tmp_path / ".agentos")
    await ensure_agentos_home(Path(home))
    await ensure_agent_workspace(home, "researcher")

    # 修改 agent 专属文件
    agent_dir = tmp_path / ".agentos" / "agents" / "researcher"
    (agent_dir / "AGENTS.md").write_text("# Researcher Instructions", encoding="utf-8")

    files = await load_workspace_files(home, agent_id="researcher")
    names = {f.name: f.content for f in files}
    assert "AGENTS.md" in names
    assert names["AGENTS.md"] == "# Researcher Instructions"


@pytest.mark.asyncio
async def test_load_workspace_files_default_agent(tmp_path):
    """默认加载 agents/default/ 的文件"""
    home = str(tmp_path / ".agentos")
    await ensure_agentos_home(Path(home))

    files = await load_workspace_files(home)
    assert len(files) == 2


@pytest.mark.asyncio
async def test_load_workspace_files_empty_file_skipped(tmp_path):
    """空文件被跳过"""
    home = str(tmp_path / ".agentos")
    await ensure_agentos_home(Path(home))

    agent_dir = tmp_path / ".agentos" / "agents" / "default"
    (agent_dir / "USER.md").write_text("", encoding="utf-8")

    files = await load_workspace_files(home)
    assert len(files) == 1
    assert files[0].name == "AGENTS.md"


@pytest.mark.asyncio
async def test_load_workspace_files_missing_dir(tmp_path):
    """目录不存在时返回空列表"""
    files = await load_workspace_files(str(tmp_path / "nonexistent"))
    assert files == []


# ── resolve_agent_workdir ──────────────────────────


def test_resolve_agent_workdir_default(tmp_path):
    """无 workdir 配置时返回 {home}/workdir/{agent_id}"""
    from dataclasses import dataclass

    @dataclass
    class FakeConfig:
        id: str = "researcher"
        workdir: str = ""

    result = resolve_agent_workdir(str(tmp_path / ".agentos"), FakeConfig())
    assert result.endswith(".agentos/workdir/researcher")


def test_resolve_agent_workdir_custom(tmp_path):
    """有 workdir 配置时直接使用"""
    from dataclasses import dataclass

    @dataclass
    class FakeConfig:
        id: str = "researcher"
        workdir: str = ""

    custom = str(tmp_path / "custom_work")
    result = resolve_agent_workdir(str(tmp_path / ".agentos"), FakeConfig(workdir=custom))
    assert result == str((tmp_path / "custom_work").resolve())


def test_resolve_agent_workdir_no_config():
    """无 agent_config 时返回 {home}/workdir/default"""
    result = resolve_agent_workdir("/tmp/home", None)
    assert result.endswith("home/workdir/default")
