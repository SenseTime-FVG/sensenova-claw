from __future__ import annotations

from pathlib import Path


def test_target_agents_include_mineru_choice_skill() -> None:
    project_root = Path(__file__).resolve().parents[2]

    expected_agents = {
        "data-analyst": project_root / ".agentos" / "agents" / "data-analyst" / "config.json",
        "doc-organizer": project_root / ".agentos" / "agents" / "doc-organizer" / "config.json",
        "search-agent": project_root / ".agentos" / "agents" / "search-agent" / "config.json",
    }

    for agent_id, config_path in expected_agents.items():
        text = config_path.read_text(encoding="utf-8")
        assert "mineru-document-extractor-choice" in text, agent_id
