from __future__ import annotations

from pathlib import Path

from sensenova_claw.capabilities.skills.registry import SkillRegistry


def _load_builtin_skills(tmp_path: Path) -> SkillRegistry:
    project_root = Path(__file__).resolve().parents[2]
    builtin_dir = project_root / ".sensenova-claw" / "skills"

    registry = SkillRegistry(
        workspace_dir=tmp_path / "skills",
        builtin_dir=builtin_dir,
    )
    registry.load_skills({})
    return registry


def test_mineru_choice_skill_can_load_without_local_cli(tmp_path: Path) -> None:
    registry = _load_builtin_skills(tmp_path)

    skill = registry.get("mineru-document-extractor-choice")

    assert skill is not None
    assert "mineru-open-api flash-extract" in skill.body
    assert "mineru-open-api extract" in skill.body
    assert (
        "curl -fsSL https://cdn-mineru.openxlab.org.cn/open-api-cli/install.sh | sh"
        in skill.body
    )
    assert "irm https://cdn-mineru.openxlab.org.cn/open-api-cli/install.ps1 | iex" in skill.body


def test_mineru_choice_skill_contains_install_and_output_contract(tmp_path: Path) -> None:
    registry = _load_builtin_skills(tmp_path)

    skill = registry.get("mineru-document-extractor-choice")

    assert skill is not None
    assert "mineru-open-api version" in skill.body
    assert "ask_user" in skill.body
    assert "官方免费快速模式" in skill.body
    assert "Token/API 完整模式" in skill.body
    assert "<workspace>/mineru_skill/<name>_<hash>/" in skill.body
    assert "不自动切换" in skill.body


def test_project_config_mentions_mineru_choice_skill() -> None:
    text = Path("config.yml").read_text(encoding="utf-8")

    assert "mineru-document-extractor-choice" in text
    assert "mineru_skill" in text
