from pathlib import Path
import tempfile
import pytest
from app.skills.registry import SkillRegistry


def test_parse_skill():
    """测试解析 SKILL.md"""
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = Path(tmpdir) / "test-skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("---\nname: test-skill\ndescription: 测试技能\n---\n\n这是技能内容\n", encoding="utf-8")

        registry = SkillRegistry()
        skill = registry._parse_skill(skill_md)

        assert skill is not None
        assert skill.name == "test-skill"
        assert skill.description == "测试技能"
        assert "这是技能内容" in skill.body


def test_load_skills():
    """测试加载 skills"""
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = Path(tmpdir) / "skill1"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: skill1\ndescription: 技能1\n---\n内容1\n", encoding="utf-8")

        registry = SkillRegistry(workspace_dir=Path(tmpdir))
        registry.load_skills({})

        skills = registry.get_all()
        assert len(skills) == 1
        assert skills[0].name == "skill1"


def test_skill_disabled():
    """测试禁用 skill"""
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = Path(tmpdir) / "skill1"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: skill1\ndescription: 技能1\n---\n内容\n", encoding="utf-8")

        config = {"skills": {"entries": {"skill1": {"enabled": False}}}}
        registry = SkillRegistry(workspace_dir=Path(tmpdir))
        registry.load_skills(config)

        assert len(registry.get_all()) == 0


def test_workspace_overrides_user():
    """测试工作区 skill 覆盖用户级 skill"""
    with tempfile.TemporaryDirectory() as user_dir, tempfile.TemporaryDirectory() as workspace_dir:
        # 用户级 skill
        user_skill = Path(user_dir) / "skill1"
        user_skill.mkdir()
        (user_skill / "SKILL.md").write_text("---\nname: skill1\ndescription: 用户级技能\n---\n用户内容\n", encoding="utf-8")

        # 工作区 skill
        ws_skill = Path(workspace_dir) / "skill1"
        ws_skill.mkdir()
        (ws_skill / "SKILL.md").write_text("---\nname: skill1\ndescription: 工作区技能\n---\n工作区内容\n", encoding="utf-8")

        registry = SkillRegistry(workspace_dir=Path(workspace_dir), user_dir=Path(user_dir))
        registry.load_skills({})

        skill = registry.get("skill1")
        assert skill is not None
        assert skill.description == "工作区技能"
