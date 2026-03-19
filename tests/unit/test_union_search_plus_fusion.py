from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace


SCRIPT_DIR = (
    Path(__file__).resolve().parents[2]
    / ".agentos"
    / "skills"
    / "union-search-plus"
    / "scripts"
)


def _load_module(name: str, filename: str):
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_deduplicate_and_rank_removes_duplicate_links() -> None:
    fusion = _load_module("search_fusion_test", "search_fusion.py")

    items = [
        {
            "title": "OpenAI Releases Model",
            "link": "https://example.com/news?utm_source=x",
            "snippet": "release details",
            "provider": "serper",
        },
        {
            "title": "OpenAI releases model",
            "link": "https://example.com/news",
            "snippet": "duplicated link",
            "provider": "union",
        },
        {
            "title": "Anthropic launches update",
            "link": "https://example.com/other",
            "snippet": "another source",
            "provider": "union",
        },
    ]

    merged = fusion.deduplicate_and_rank(items, query="openai model")
    assert len(merged) == 2
    assert all(item.get("title") for item in merged)
    assert all(item.get("link") for item in merged)


def test_assess_insufficiency_hits_thresholds() -> None:
    fusion = _load_module("search_fusion_test2", "search_fusion.py")

    items = [
        {
            "title": "Only one source",
            "link": "https://example.com/1",
            "snippet": "tiny",
            "provider": "serper",
        }
    ]

    result = fusion.assess_insufficiency(
        items=items,
        query="agent platform comparison",
        min_sources=3,
        min_topic_coverage=0.5,
        min_valid_evidence=4,
    )

    assert result["is_insufficient"] is True
    assert result["metrics"]["source_count"] == 1
    assert result["metrics"]["valid_evidence_count"] == 1
    assert len(result["reasons"]) >= 1


def test_union_search_plus_adapts_vendor_envelope(monkeypatch) -> None:
    mod = _load_module("union_search_plus_test", "union_search_plus.py")

    stdout_payload = {
        "success": True,
        "data": {
            "results": {
                "serper": {
                    "items": [
                        {
                            "title": "AgentOS",
                            "link": "https://example.com/agentos",
                            "snippet": "event driven",
                        }
                    ]
                },
                "wikipedia": {
                    "items": [
                        {
                            "title": "AgentOS",
                            "link": "https://example.com/agentos?utm_source=wiki",
                            "snippet": "duplicate",
                        }
                    ]
                },
            }
        },
    }

    def _fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=json.dumps(stdout_payload), stderr="")

    monkeypatch.setattr(mod.subprocess, "run", _fake_run)

    result = mod.run_union_search(
        query="agentos",
        group="preferred",
        limit=5,
        timeout=60,
        env_file=".env",
    )

    assert result["success"] is True
    assert result["provider"] == "union-search-plus"
    assert result["summary"]["raw_items"] == 2
    assert result["summary"]["total_items"] == 1
