"""SkillRegistry 扩展功能单测：install_info、热重载、启用状态持久化"""
import json
import pytest
from pathlib import Path
from agentos.capabilities.skills.registry import Skill, SkillRegistry


@pytest.fixture
def tmp_workspace(tmp_path):
    skill_dir = tmp_path / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: test-skill\ndescription: A test skill\n---\nDo something with $ARGUMENTS"
    )
    return tmp_path


@pytest.fixture
def tmp_skill(tmp_workspace):
    skill_dir = tmp_workspace / "skills" / "test-skill"
    return Skill(
        name="test-skill",
        description="A test skill",
        body="Do something with $ARGUMENTS",
        path=skill_dir,
    )


def test_install_info_none_when_no_file(tmp_skill):
    assert tmp_skill.install_info is None
    assert tmp_skill.source == "local"
    assert tmp_skill.version is None


def test_install_info_reads_json(tmp_skill):
    info = {"source": "clawhub", "source_id": "test-skill", "version": "1.0.0"}
    (tmp_skill.path / ".install.json").write_text(json.dumps(info))
    assert tmp_skill.install_info["source"] == "clawhub"
    assert tmp_skill.source == "clawhub"
    assert tmp_skill.version == "1.0.0"


def test_register_and_unregister(tmp_skill):
    reg = SkillRegistry()
    reg.register(tmp_skill)
    assert reg.get("test-skill") is not None
    assert reg.unregister("test-skill") is True
    assert reg.get("test-skill") is None
    assert reg.unregister("nonexistent") is False


def test_reload_skill(tmp_workspace):
    reg = SkillRegistry(workspace_dir=tmp_workspace / "skills")
    reg.load_skills({})
    assert reg.get("test-skill") is not None
    skill_md = tmp_workspace / "skills" / "test-skill" / "SKILL.md"
    skill_md.write_text("---\nname: test-skill\ndescription: Updated desc\n---\nNew body")
    assert reg.reload_skill("test-skill", {}) is True
    assert reg.get("test-skill").description == "Updated desc"
    assert reg.reload_skill("nonexistent", {}) is False


def test_skills_state_json_persistence(tmp_workspace):
    state_file = tmp_workspace / "skills_state.json"
    reg = SkillRegistry(workspace_dir=tmp_workspace / "skills", state_file=state_file)
    reg.load_skills({})
    assert reg.get("test-skill") is not None
    reg.set_enabled("test-skill", False)
    state = json.loads(state_file.read_text())
    assert state["test-skill"]["enabled"] is False
    reg2 = SkillRegistry(workspace_dir=tmp_workspace / "skills", state_file=state_file)
    reg2.load_skills({})
    assert reg2.get("test-skill") is None
    reg2.set_enabled("test-skill", True)
    reg2.load_skills({})
    assert reg2.get("test-skill") is not None
