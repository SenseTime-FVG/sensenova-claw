"""Git URL 适配器 -- 从 Git 仓库克隆并提取 skill"""
from __future__ import annotations

import asyncio
import shutil
import tempfile
import logging
from pathlib import Path

from app.skills.models import SearchResult, SkillDetail, UpdateInfo
from .base import MarketAdapter

logger = logging.getLogger(__name__)


class GitAdapter(MarketAdapter):
    @property
    def supports_search(self) -> bool:
        return False

    async def search(self, query: str, page: int = 1, page_size: int = 20) -> SearchResult:
        return SearchResult(source="git", total=0, page=page, page_size=page_size, items=[])

    async def get_detail(self, skill_id: str) -> SkillDetail:
        tmp_dir = Path(tempfile.mkdtemp())
        try:
            await self._clone(skill_id, tmp_dir)
            skill_md_path = self._find_skill_md(tmp_dir)
            if not skill_md_path:
                raise FileNotFoundError(f"仓库中未找到 SKILL.md: {skill_id}")

            content = skill_md_path.read_text(encoding="utf-8")
            skill_dir = skill_md_path.parent
            files = [
                str(f.relative_to(skill_dir))
                for f in skill_dir.rglob("*")
                if f.is_file() and not f.name.startswith(".")
            ]
            name = skill_dir.name
            description = ""
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    import yaml
                    fm = yaml.safe_load(parts[1]) or {}
                    name = fm.get("name", name)
                    description = fm.get("description", "")

            return SkillDetail(
                id=skill_id, name=name, description=description,
                skill_md_preview=content, files=files, installed=False,
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def download(self, skill_id: str, target_dir: Path) -> Path:
        tmp_dir = Path(tempfile.mkdtemp())
        try:
            await self._clone(skill_id, tmp_dir)
            skill_md_path = self._find_skill_md(tmp_dir)
            if not skill_md_path:
                raise FileNotFoundError(f"仓库中未找到 SKILL.md: {skill_id}")

            skill_src = skill_md_path.parent
            skill_name = skill_src.name
            skill_dst = target_dir / skill_name

            if skill_dst.exists():
                raise FileExistsError(f"目标目录已存在: {skill_dst}")

            shutil.copytree(skill_src, skill_dst)
            git_dir = skill_dst / ".git"
            if git_dir.exists():
                shutil.rmtree(git_dir)
            return skill_dst
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def check_update(self, skill_id: str, current_version: str) -> UpdateInfo | None:
        return None

    async def _clone(self, repo_url: str, dest: Path) -> None:
        # 仅允许远程协议，防止 file:// 等本地访问
        if not (repo_url.startswith("https://") or repo_url.startswith("git@") or repo_url.startswith("ssh://")):
            raise ValueError(f"不支持的 repo_url 协议: {repo_url}")
        proc = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth", "1", repo_url, str(dest / "repo"),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"git clone 失败: {stderr.decode()}")

    def _find_skill_md(self, base: Path) -> Path | None:
        for p in base.rglob("SKILL.md"):
            return p
        return None
