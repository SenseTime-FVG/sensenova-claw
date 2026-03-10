from __future__ import annotations

import shutil
import yaml
from pathlib import Path
from typing import Any


class Skill:
    def __init__(self, name: str, description: str, body: str, path: Path):
        self.name = name
        self.description = description
        self.body = body
        self.path = path


class SkillRegistry:
    def __init__(self, workspace_dir: Path | None = None, user_dir: Path | None = None):
        self._skills: dict[str, Skill] = {}
        self._workspace_dir = workspace_dir
        self._user_dir = user_dir or Path.home() / ".agentos" / "skills"

    def load_skills(self, config: dict[str, Any]) -> None:
        """从用户目录、工作区目录和额外目录加载 skills"""
        # 先加载用户级 skills
        if self._user_dir.exists():
            self._load_from_dir(self._user_dir, config)

        # 再加载工作区 skills（覆盖同名）
        if self._workspace_dir and self._workspace_dir.exists():
            self._load_from_dir(self._workspace_dir, config)

        # 加载 extra_dirs 中配置的额外 skill 目录
        extra_dirs = config.get("skills", {}).get("extra_dirs", [])
        for dir_path in extra_dirs:
            p = Path(dir_path)
            if p.exists():
                self._load_from_dir(p, config)

    def _load_from_dir(self, base_dir: Path, config: dict[str, Any]) -> None:
        """从目录加载所有 SKILL.md"""
        for skill_md in base_dir.rglob("SKILL.md"):
            skill = self._parse_skill(skill_md)
            if skill and self._should_load(skill, config):
                self._skills[skill.name] = skill

    def _parse_skill(self, skill_path: Path) -> Skill | None:
        """解析 SKILL.md 文件"""
        try:
            content = skill_path.read_text(encoding="utf-8")
            if not content.startswith("---"):
                return None

            parts = content.split("---", 2)
            if len(parts) < 3:
                return None

            frontmatter = yaml.safe_load(parts[1])
            name = frontmatter.get("name")
            description = frontmatter.get("description")
            body = parts[2].strip()

            if not name or not description:
                return None

            return Skill(name, description, body, skill_path.parent)
        except Exception:
            return None

    def _should_load(self, skill: Skill, config: dict[str, Any]) -> bool:
        """检查 skill 是否应该加载（门控）"""
        # 检查配置中是否禁用
        entries = config.get("skills", {}).get("entries", {})
        skill_config = entries.get(skill.name, {})
        if not skill_config.get("enabled", True):
            return False

        # 检查依赖的二进制文件
        metadata = self._parse_metadata(skill)
        requires = metadata.get("agentos", {}).get("requires", {})
        bins = requires.get("bins", [])
        for bin_name in bins:
            if not shutil.which(bin_name):
                return False

        return True

    def _parse_metadata(self, skill: Skill) -> dict[str, Any]:
        """解析 frontmatter 中的 metadata 字段"""
        try:
            skill_md = skill.path / "SKILL.md"
            content = skill_md.read_text(encoding="utf-8")
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = yaml.safe_load(parts[1])
                return frontmatter.get("metadata", {})
        except Exception:
            pass
        return {}

    def get_all(self) -> list[Skill]:
        """获取所有已加载的 skills"""
        return list(self._skills.values())

    def get(self, name: str) -> Skill | None:
        """根据名称获取 skill"""
        return self._skills.get(name)
