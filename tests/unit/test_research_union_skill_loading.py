from __future__ import annotations

from pathlib import Path

from agentos.capabilities.skills.registry import SkillRegistry


def test_research_union_and_union_search_plus_can_be_loaded(tmp_path: Path) -> None:
    """验证新增技能可被 SkillRegistry 加载。"""
    project_root = Path(__file__).resolve().parents[2]
    builtin_dir = project_root / ".agentos" / "skills"

    registry = SkillRegistry(workspace_dir=tmp_path / "skills", builtin_dir=builtin_dir)
    registry.load_skills({})

    research_union = registry.get("research-union")
    union_plus = registry.get("union-search-plus")

    assert research_union is not None
    assert union_plus is not None
    assert "outline" in research_union.body
    assert "preferred" in union_plus.body
