from __future__ import annotations

import json
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

    @property
    def install_info(self) -> dict[str, Any] | None:
        """读取 .install.json，返回安装信息字典或 None"""
        install_file = self.path / ".install.json"
        if not install_file.exists():
            return None
        try:
            return json.loads(install_file.read_text(encoding="utf-8"))
        except Exception:
            return None

    @property
    def source(self) -> str:
        """返回 skill 来源，默认 'local'"""
        info = self.install_info
        if info:
            return info.get("source", "local")
        return "local"

    @property
    def version(self) -> str | None:
        """返回 skill 版本号，无安装信息时返回 None"""
        info = self.install_info
        if info:
            return info.get("version")
        return None


class SkillRegistry:
    def __init__(
        self,
        workspace_dir: Path | None = None,
        user_dir: Path | None = None,
        state_file: Path | None = None,
        builtin_dir: Path | None = None,
    ):
        self._skills: dict[str, Skill] = {}
        self._workspace_dir = workspace_dir
        self._user_dir = user_dir or Path.home() / ".sensenova-claw" / "skills"
        self._state_file = state_file
        self._builtin_dir = builtin_dir

    # ---- 状态持久化 ----

    def _load_state(self) -> dict[str, Any]:
        """读取 skills_state.json"""
        if self._state_file and self._state_file.exists():
            try:
                return json.loads(self._state_file.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_state(self, state: dict[str, Any]) -> None:
        """写入 skills_state.json"""
        if self._state_file:
            self._state_file.write_text(
                json.dumps(state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def set_enabled(self, name: str, enabled: bool) -> None:
        """设置 skill 启用/禁用状态并持久化"""
        state = self._load_state()
        if name not in state:
            state[name] = {}
        state[name]["enabled"] = enabled
        self._save_state(state)

        # 如果禁用，立即从内存中移除
        if not enabled:
            self._skills.pop(name, None)

    def is_enabled(self, name: str) -> bool:
        """检查 skill 是否启用"""
        state = self._load_state()
        skill_state = state.get(name, {})
        return skill_state.get("enabled", True)

    # ---- 热重载 ----

    def register(self, skill: Skill) -> None:
        """注册一个 skill 到内存"""
        self._skills[skill.name] = skill

    def unregister(self, name: str) -> bool:
        """从内存移除一个 skill，返回是否成功"""
        if name in self._skills:
            del self._skills[name]
            return True
        return False

    def reload_skill(self, name: str, config: dict[str, Any]) -> bool:
        """重新加载指定 skill，返回是否成功"""
        # 查找已有 skill 的路径
        old_skill = self._skills.get(name)
        if old_skill is None:
            return False

        skill_md = old_skill.path / "SKILL.md"
        if not skill_md.exists():
            return False

        new_skill = self._parse_skill(skill_md)
        if new_skill is None:
            return False

        if self._should_load(new_skill, config):
            self._skills[new_skill.name] = new_skill
        else:
            self._skills.pop(name, None)
        return True

    def parse_skill(self, skill_path: Path) -> Skill | None:
        """公开的 skill 解析方法"""
        return self._parse_skill(skill_path)

    # ---- 加载 ----

    def load_skills(self, config: dict[str, Any]) -> None:
        """从内置目录、用户目录、工作区目录和额外目录加载 skills
        
        加载优先级（后加载的覆盖先加载的同名 skill）：
        builtin < user < workspace < extra_dirs
        """
        self._skills.clear()

        # 最先加载内置 skills（最低优先级）
        if self._builtin_dir and self._builtin_dir.exists():
            self._load_from_dir(self._builtin_dir, config)

        # 加载用户级 skills
        if self._user_dir.exists():
            self._load_from_dir(self._user_dir, config)

        # 加载工作区 skills（覆盖同名）
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
        """检查 skill 是否应该加载（门控）

        优先级: skills_state.json > config.yml entries > 默认 True
        """
        # 1. 优先检查 skills_state.json
        state = self._load_state()
        if skill.name in state:
            if not state[skill.name].get("enabled", True):
                return False
            # 如果 state 中存在且 enabled=True，跳过 config 检查
            return self._check_binary_deps(skill)

        # 2. 检查 config.yml 中的配置
        entries = config.get("skills", {}).get("entries", {})
        skill_config = entries.get(skill.name, {})
        if not skill_config.get("enabled", True):
            return False

        # 3. 检查依赖的二进制文件
        return self._check_binary_deps(skill)

    def _check_binary_deps(self, skill: Skill) -> bool:
        """检查 skill 所需的二进制依赖是否可用"""
        metadata = self._parse_metadata(skill)
        requires = (metadata.get("sensenova-claw") or metadata.get("sensenova_claw") or {}).get("requires", {})
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
