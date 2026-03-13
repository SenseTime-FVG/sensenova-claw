"""GitAdapter 单元测试"""
import shutil
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

from agentos.adapters.skill_sources.git_adapter import GitAdapter


def _setup_repo(base: Path, files: dict[str, str], repo_subdir: str = "repo") -> Path:
    """在 base 下模拟 git clone 的结果目录"""
    repo_dir = base / repo_subdir
    for fpath, content in files.items():
        full = repo_dir / fpath
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
    return repo_dir


class TestGitAdapterProperties:
    def test_supports_search_返回false(self):
        assert GitAdapter().supports_search is False

    def test_supports_browse_默认false(self):
        assert GitAdapter().supports_browse is False


class TestGitAdapterSearch:
    async def test_search_返回空结果(self):
        result = await GitAdapter().search("anything")
        assert result.source == "git"
        assert result.total == 0
        assert result.items == []


class TestGitAdapterGetDetail:
    async def test_get_detail_正常(self, tmp_path):
        """有 SKILL.md 的仓库应正确返回详情"""
        skill_md = """---
name: My Skill
description: A cool skill
---
# My Skill Content"""

        adapter = GitAdapter()

        async def mock_clone(repo_url, dest):
            _setup_repo(dest, {
                "my-skill/SKILL.md": skill_md,
                "my-skill/run.py": "print(1)",
            })

        with patch.object(adapter, "_clone", side_effect=mock_clone):
            with patch("agentos.adapters.skill_sources.git_adapter.tempfile.mkdtemp", return_value=str(tmp_path)):
                detail = await adapter.get_detail("https://github.com/user/repo.git")

        assert detail.name == "My Skill"
        assert detail.description == "A cool skill"
        assert "My Skill Content" in detail.skill_md_preview
        assert "run.py" in detail.files

    async def test_get_detail_无SKILL_md抛异常(self, tmp_path):
        """仓库中没有 SKILL.md 应抛 FileNotFoundError"""
        adapter = GitAdapter()

        async def mock_clone(repo_url, dest):
            _setup_repo(dest, {"readme.md": "hello"})

        with patch.object(adapter, "_clone", side_effect=mock_clone):
            with patch("agentos.adapters.skill_sources.git_adapter.tempfile.mkdtemp", return_value=str(tmp_path)):
                with pytest.raises(FileNotFoundError, match="SKILL.md"):
                    await adapter.get_detail("https://github.com/user/repo.git")

    async def test_get_detail_无frontmatter(self, tmp_path):
        """SKILL.md 没有 YAML frontmatter 时使用目录名"""
        adapter = GitAdapter()

        async def mock_clone(repo_url, dest):
            _setup_repo(dest, {"some-skill/SKILL.md": "# Just content"})

        with patch.object(adapter, "_clone", side_effect=mock_clone):
            with patch("agentos.adapters.skill_sources.git_adapter.tempfile.mkdtemp", return_value=str(tmp_path)):
                detail = await adapter.get_detail("https://github.com/user/repo.git")

        assert detail.name == "some-skill"
        assert detail.description == ""


class TestGitAdapterDownload:
    async def test_download_正常(self, tmp_path):
        """正常下载并拷贝到目标目录"""
        clone_dir = tmp_path / "clone_tmp"
        clone_dir.mkdir()
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        adapter = GitAdapter()

        async def mock_clone(repo_url, dest):
            _setup_repo(dest, {
                "my-skill/SKILL.md": "# Skill",
                "my-skill/main.py": "pass",
                "my-skill/.git/config": "git stuff",
            })

        with patch.object(adapter, "_clone", side_effect=mock_clone):
            with patch("agentos.adapters.skill_sources.git_adapter.tempfile.mkdtemp", return_value=str(clone_dir)):
                result = await adapter.download("https://github.com/user/repo.git", target_dir)

        assert result == target_dir / "my-skill"
        assert (result / "SKILL.md").exists()
        assert (result / "main.py").exists()
        # .git 目录应被删除
        assert not (result / ".git").exists()

    async def test_download_目标已存在抛异常(self, tmp_path):
        """目标目录已存在应抛 FileExistsError"""
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        # 预先创建同名目录
        (target_dir / "my-skill").mkdir()

        adapter = GitAdapter()

        async def mock_clone(repo_url, dest):
            _setup_repo(dest, {"my-skill/SKILL.md": "# Skill"})

        with patch.object(adapter, "_clone", side_effect=mock_clone):
            with patch("agentos.adapters.skill_sources.git_adapter.tempfile.mkdtemp", return_value=str(tmp_path / "clonetmp")):
                (tmp_path / "clonetmp").mkdir()
                with pytest.raises(FileExistsError, match="已存在"):
                    await adapter.download("https://github.com/user/repo.git", target_dir)

    async def test_download_无SKILL_md抛异常(self, tmp_path):
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        clone_dir = tmp_path / "clone_tmp"
        clone_dir.mkdir()

        adapter = GitAdapter()

        async def mock_clone(repo_url, dest):
            _setup_repo(dest, {"readme.md": "hello"})

        with patch.object(adapter, "_clone", side_effect=mock_clone):
            with patch("agentos.adapters.skill_sources.git_adapter.tempfile.mkdtemp", return_value=str(clone_dir)):
                with pytest.raises(FileNotFoundError, match="SKILL.md"):
                    await adapter.download("https://github.com/user/repo.git", target_dir)


class TestGitAdapterCheckUpdate:
    async def test_check_update_始终返回none(self):
        result = await GitAdapter().check_update("https://github.com/user/repo.git", "1.0")
        assert result is None


class TestGitAdapterClone:
    async def test_clone_拒绝file协议(self):
        adapter = GitAdapter()
        with pytest.raises(ValueError, match="不支持的 repo_url 协议"):
            await adapter._clone("file:///etc/passwd", Path("/tmp/test"))

    async def test_clone_拒绝本地路径(self):
        adapter = GitAdapter()
        with pytest.raises(ValueError, match="不支持的 repo_url 协议"):
            await adapter._clone("/local/path", Path("/tmp/test"))

    async def test_clone_接受https(self):
        """https:// 协议应被接受（模拟 git clone 成功）"""
        adapter = GitAdapter()
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("agentos.adapters.skill_sources.git_adapter.asyncio.create_subprocess_exec",
                    new_callable=AsyncMock, return_value=mock_proc):
            await adapter._clone("https://github.com/user/repo.git", Path("/tmp/test"))

    async def test_clone_接受git_at(self):
        """git@ 协议应被接受"""
        adapter = GitAdapter()
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("agentos.adapters.skill_sources.git_adapter.asyncio.create_subprocess_exec",
                    new_callable=AsyncMock, return_value=mock_proc):
            await adapter._clone("git@github.com:user/repo.git", Path("/tmp/test"))

    async def test_clone_失败抛RuntimeError(self):
        adapter = GitAdapter()
        mock_proc = MagicMock()
        mock_proc.returncode = 128
        mock_proc.communicate = AsyncMock(return_value=(b"", b"fatal: not found"))

        with patch("agentos.adapters.skill_sources.git_adapter.asyncio.create_subprocess_exec",
                    new_callable=AsyncMock, return_value=mock_proc):
            with pytest.raises(RuntimeError, match="git clone 失败"):
                await adapter._clone("https://github.com/user/repo.git", Path("/tmp/test"))
