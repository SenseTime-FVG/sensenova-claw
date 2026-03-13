"""S01: SkillRegistry 加载/分类/启停"""
from pathlib import Path
from app.skills.registry import SkillRegistry, Skill


def _create_skill_dir(base: Path, name: str, desc: str = "test") -> Path:
    """创建一个最小的 SKILL.md"""
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\nBody of {name}",
        encoding="utf-8",
    )
    return d


class TestSkillRegistry:
    def test_register_get(self, tmp_path):
        r = SkillRegistry()
        s = Skill("test_skill", "A test skill", "body", tmp_path)
        r.register(s)
        assert r.get("test_skill") is not None
        assert r.get("test_skill").description == "A test skill"

    def test_unregister(self, tmp_path):
        r = SkillRegistry()
        s = Skill("rm", "R", "b", tmp_path)
        r.register(s)
        assert r.unregister("rm") is True
        assert r.get("rm") is None
        assert r.unregister("rm") is False

    def test_get_all(self, tmp_path):
        r = SkillRegistry()
        r.register(Skill("a", "A", "b", tmp_path))
        r.register(Skill("b", "B", "b", tmp_path))
        assert len(r.get_all()) == 2

    def test_set_enabled(self, tmp_path):
        state_file = tmp_path / "state.json"
        r = SkillRegistry(state_file=state_file)
        s = Skill("tog", "T", "b", tmp_path)
        r.register(s)
        r.set_enabled("tog", False)
        assert r.is_enabled("tog") is False
        r.set_enabled("tog", True)
        assert r.is_enabled("tog") is True

    def test_load_from_dir(self, tmp_path):
        ws = tmp_path / "skills"
        _create_skill_dir(ws, "my_skill", "My Skill")
        r = SkillRegistry(workspace_dir=ws)
        r.load_skills({})
        assert r.get("my_skill") is not None
        assert r.get("my_skill").description == "My Skill"

    def test_parse_skill_invalid(self, tmp_path):
        r = SkillRegistry()
        # 空文件
        bad = tmp_path / "bad" / "SKILL.md"
        bad.parent.mkdir(parents=True)
        bad.write_text("no frontmatter here", encoding="utf-8")
        assert r.parse_skill(bad) is None

    def test_disabled_skill_not_loaded(self, tmp_path):
        ws = tmp_path / "skills"
        _create_skill_dir(ws, "disabled_s", "DS")
        state_file = tmp_path / "state.json"
        r = SkillRegistry(workspace_dir=ws, state_file=state_file)
        r.set_enabled("disabled_s", False)
        r.load_skills({})
        assert r.get("disabled_s") is None
