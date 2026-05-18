import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / ".sensenova-claw"
    / "skills"
    / "search-academic"
    / "scripts"
    / "refTree.py"
)


def _load_module(name="search_academic_ref_tree"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_default_direction_uses_semantic_official_for_references_and_citations(monkeypatch):
    module = _load_module("search_academic_ref_tree_default")
    calls = []

    def fake_call_provider_with_timeout(provider, paper_id, title, direction, limit, timeout_seconds, api_key=None):
        calls.append((provider.provider, paper_id, title, direction, limit, api_key))
        return {
            "success": True,
            "paper_id": paper_id,
            "direction": direction,
            "items": [
                {
                    "paper_id": f"{direction}-paper",
                    "title": f"{direction.title()} Paper",
                    "snippet": f"{direction} abstract",
                    "citation_count": 12,
                    "doi": f"10.1234/{direction}",
                }
            ],
            "error": None,
        }

    monkeypatch.setattr(module, "_call_provider_with_timeout", fake_call_provider_with_timeout)

    result = module.ref_tree("source-paper", "Source Title", sources=["semantic"], limit=1, api_key="key")

    assert set(calls) == {
        ("semantic_official", "source-paper", "Source Title", "references", 1, "key"),
        ("semantic_official", "source-paper", "Source Title", "citations", 1, "key"),
    }
    assert result["success"] is True
    assert result["id"] == "source-paper"
    assert result["title"] == "Source Title"
    assert result["provider"] == "refTree.py"
    assert "provider_rating" not in result
    assert "references" not in result
    assert "citations" not in result
    assert result["source_results"][0]["references"] == [
        {
            "source": "semantic",
            "id": "references-paper",
            "title": "References Paper",
            "provider": "semantic_official",
            "provider_rating": None,
            "citation_count": 12,
            "abstract": "references abstract",
            "paper_id": "references-paper",
            "doi": "10.1234/references",
            "snippet": "references abstract",
        }
    ]
    assert result["source_results"][0]["citations"][0]["provider"] == "semantic_official"
    assert result["source_results"][0]["citations"][0]["id"] == "citations-paper"


def test_single_failed_default_direction_falls_back_to_crawler_only_for_that_direction(monkeypatch):
    module = _load_module("search_academic_ref_tree_partial_fallback")
    calls = []

    def fake_call_provider_with_timeout(provider, paper_id, title, direction, limit, timeout_seconds, api_key=None):
        calls.append((provider.provider, direction))
        if provider.provider == "semantic_official" and direction == "references":
            raise RuntimeError("official references failed")
        if provider.provider == "semantic_official":
            return {
                "success": True,
                "paper_id": paper_id,
                "direction": direction,
                "items": [{"paper_id": "citing-1", "title": "Citing", "citation_count": 3}],
                "error": None,
            }
        return {
            "query": title,
            "direction": direction,
            "references": [{"url": "https://www.semanticscholar.org/paper/ref-1", "title": "Referenced", "citation_count": 7}],
            "references_count": 1,
        }

    monkeypatch.setattr(module, "_call_provider_with_timeout", fake_call_provider_with_timeout)

    result = module.ref_tree("source-paper", "Source Title", limit=1)

    assert calls.count(("semantic_crawler", "references")) == 1
    assert ("semantic_crawler", "citations") not in calls
    assert result["success"] is True
    assert result["provider"] == "refTree.py"
    assert "references" not in result
    assert "citations" not in result
    assert result["source_results"][0]["references"][0]["provider"] == "semantic_crawler"
    assert result["source_results"][0]["references"][0]["id"] == "ref-1"
    assert result["source_results"][0]["citations"][0]["provider"] == "semantic_official"
    assert result["source_results"][0]["attempts"] == [
        {"provider": "semantic_official", "direction": "references", "success": False, "count": 0, "error": "official references failed"},
        {"provider": "semantic_official", "direction": "citations", "success": True, "count": 1, "error": None},
        {"provider": "semantic_crawler", "direction": "references", "success": True, "count": 1, "error": None},
    ]


def test_both_default_directions_failed_uses_one_crawler_call_without_direction(monkeypatch):
    module = _load_module("search_academic_ref_tree_full_fallback")
    calls = []

    def fake_call_provider_with_timeout(provider, paper_id, title, direction, limit, timeout_seconds, api_key=None):
        calls.append((provider.provider, direction))
        if provider.provider == "semantic_official":
            raise RuntimeError(f"{direction} failed")
        assert direction is None
        return {
            "query": title,
            "direction": "all",
            "references": [{"url": "https://www.semanticscholar.org/paper/ref-1", "title": "Referenced", "citation_count": 7}],
            "citations": [{"url": "https://www.semanticscholar.org/paper/cite-1", "title": "Citing", "citation_count": 9}],
        }

    monkeypatch.setattr(module, "_call_provider_with_timeout", fake_call_provider_with_timeout)

    result = module.ref_tree("source-paper", "Source Title", limit=1)

    assert set(calls[:2]) == {
        ("semantic_official", "references"),
        ("semantic_official", "citations"),
    }
    assert calls[2:] == [("semantic_crawler", None)]
    assert result["success"] is True
    assert result["provider"] == "refTree.py"
    assert "references" not in result
    assert "citations" not in result
    assert result["source_results"][0]["references"][0]["id"] == "ref-1"
    assert result["source_results"][0]["citations"][0]["id"] == "cite-1"


def test_call_provider_passes_only_supported_arguments(monkeypatch):
    module = _load_module("search_academic_ref_tree_provider_kwargs")
    recorded = {}

    def fake_fetch_refs(paper_id, direction, limit, min_citations, year_min, year_max, api_key=None):
        recorded["official"] = {
            "paper_id": paper_id,
            "direction": direction,
            "limit": limit,
            "min_citations": min_citations,
            "year_min": year_min,
            "year_max": year_max,
            "api_key": api_key,
        }
        return {"success": True, "direction": direction, "items": []}

    async def fake_crawl(title, output, headless, limit, max_pages, direction=None):
        recorded["crawler"] = {
            "title": title,
            "output_name": output.name,
            "headless": headless,
            "limit": limit,
            "max_pages": max_pages,
            "direction": direction,
        }
        return {"direction": direction, "references": [], "citations": []}

    def fake_import_module(name):
        if name == "semantic_scholar_refTree":
            return type("OfficialModule", (), {"fetch_refs": staticmethod(fake_fetch_refs)})
        if name == "semantic_scholar_crawler_refTree":
            return type("CrawlerModule", (), {"crawl": staticmethod(fake_crawl)})
        raise AssertionError(f"unexpected import {name}")

    monkeypatch.setattr(module.importlib, "import_module", fake_import_module)

    module._call_provider(module.PROVIDER_GROUPS["semantic"][0], "paper-1", "Source Title", "references", 4, api_key="key")
    module._call_provider(module.PROVIDER_GROUPS["semantic"][1], "paper-1", "Source Title", "citations", 5, api_key="key")

    assert recorded["official"] == {
        "paper_id": "paper-1",
        "direction": "references",
        "limit": 4,
        "min_citations": 0,
        "year_min": None,
        "year_max": None,
        "api_key": "key",
    }
    assert recorded["crawler"] == {
        "title": "Source Title",
        "output_name": "ref_tree_output.json",
        "headless": True,
        "limit": 5,
        "max_pages": None,
        "direction": "citations",
    }


def test_main_writes_unified_output_file(monkeypatch, capsys, tmp_path):
    module = _load_module("search_academic_ref_tree_cli")
    output_path = tmp_path / "nested" / "tree.json"

    def fake_ref_tree(paper_id, title, sources=None, direction=None, limit=10, provider_timeout=60, api_key=None):
        return {
            "success": True,
            "id": paper_id,
            "title": title,
            "provider": "refTree.py",
            "sources": sources,
            "direction": direction or "all",
            "source_results": [
                {
                    "source": "semantic",
                    "success": True,
                    "provider": "semantic_official",
                    "citations": [],
                    "references": [{"id": "r1", "title": "Reference"}],
                    "attempts": [],
                    "error": None,
                }
            ],
            "errors": [],
            "error": None,
        }

    monkeypatch.setattr(module, "ref_tree", fake_ref_tree)
    monkeypatch.setattr(
        sys,
        "argv",
        ["refTree.py", "--paper_id", "paper-1", "--title", "Source Title", "--source", "semantic", "--direction", "references", "--limit", "3", "--output", str(output_path)],
    )

    module.main()

    stdout_json = json.loads(capsys.readouterr().out)
    file_json = json.loads(output_path.read_text(encoding="utf-8"))
    expected = {
        "success": True,
        "id": "paper-1",
        "title": "Source Title",
        "provider": "refTree.py",
        "sources": ["semantic"],
        "direction": "references",
        "source_results": [
            {
                "source": "semantic",
                "success": True,
                "provider": "semantic_official",
                "citations": [],
                "references": [{"id": "r1", "title": "Reference"}],
                "attempts": [],
                "error": None,
            }
        ],
        "errors": [],
        "error": None,
        "output_path": str(output_path.resolve()),
    }
    assert stdout_json == expected
    assert file_json == expected


def test_cli_rejects_positional_paper_id():
    module = _load_module("search_academic_ref_tree_cli_paper_id")

    with pytest.raises(SystemExit):
        module.build_parser().parse_args(["paper-1", "--title", "Source Title"])
