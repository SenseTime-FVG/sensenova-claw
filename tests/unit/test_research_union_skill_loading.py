from __future__ import annotations

from pathlib import Path

from sensenova_claw.capabilities.skills.registry import SkillRegistry


def test_research_union_loads_and_union_search_plus_is_removed(tmp_path: Path) -> None:
    """验证 research-union 可加载，且 union-search-plus 已移除。"""
    project_root = Path(__file__).resolve().parents[2]
    builtin_dir = project_root / ".sensenova-claw" / "skills"

    registry = SkillRegistry(workspace_dir=tmp_path / "skills", builtin_dir=builtin_dir)
    registry.load_skills({})

    research_union = registry.get("research-union")
    assert research_union is not None
    assert "PLAN → DIVERGE → SEARCH" in research_union.body
    assert registry.get("union-search-plus") is None
