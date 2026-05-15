import importlib.util
import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / ".sensenova-claw"
    / "skills"
    / "search-academic"
    / "scripts"
    / "search.py"
)


def _load_module(name="search_academic_unified_search"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_arxiv_source_uses_fallback_order_and_normalizes_items(monkeypatch):
    module = _load_module("search_academic_unified_search_fallback")
    calls = []

    def fake_call_provider(provider, query, limit, category, lang=None):
        calls.append((provider.module_name, query, limit, category))
        if provider.module_name == "arxiv_search":
            raise RuntimeError("official unavailable")
        if provider.module_name == "deepxiv_search":
            return [
                {
                    "title": "DeepXiv Paper",
                    "url": "https://arxiv.org/abs/2401.00001",
                    "snippet": "Fallback abstract",
                    "arxiv_id": "2401.00001",
                    "citation_count": 12,
                }
            ]
        raise AssertionError(f"unexpected provider {provider.module_name}")

    monkeypatch.setattr(module, "_call_provider", fake_call_provider)

    result = module.search("NSA", sources=["arxiv"], limit=3, category="cs.CL")

    assert calls == [
        ("arxiv_search", "NSA", 3, "cs.CL"),
        ("deepxiv_search", "NSA", 3, "cs.CL"),
    ]
    assert result["success"] is True
    assert result["query"] == "NSA"
    assert result["provider"] == "search.py"
    assert result["error"] is None
    assert result["items"] == [
        {
            "source": "arxiv",
            "provider": "deepxiv",
            "provider_rating": None,
            "title": "DeepXiv Paper",
            "abstract": "Fallback abstract",
            "citation_count": 12,
            "url": "https://arxiv.org/abs/2401.00001",
            "snippet": "Fallback abstract",
            "arxiv_id": "2401.00001",
        }
    ]


def test_call_provider_only_passes_supported_category_kwargs(monkeypatch):
    module = _load_module("search_academic_unified_search_kwargs")
    recorded = {}

    def fake_import_module(name):
        def fake_search(query, limit, **kwargs):
            recorded[name] = (query, limit, kwargs)
            return [{"title": name, "url": "", "snippet": ""}]

        return SimpleNamespace(search=fake_search)

    monkeypatch.setattr(module.importlib, "import_module", fake_import_module)

    module._call_provider(module.PROVIDER_GROUPS["arxiv"][0], "q", 5, "cs.CL")
    module._call_provider(module.PROVIDER_GROUPS["arxiv"][1], "q", 5, "cs.CL")
    module._call_provider(module.PROVIDER_GROUPS["arxiv"][2], "q", 5, "cs.CL")

    assert recorded["arxiv_search"] == ("q", 5, {"category": "cs.CL"})
    assert recorded["deepxiv_search"] == ("q", 5, {"categories": ["cs.CL"]})
    assert recorded["openalex_search"] == ("q", 5, {})


def test_wikipedia_provider_receives_only_supported_kwargs(monkeypatch):
    module = _load_module("search_academic_unified_search_wikipedia_kwargs")
    recorded = {}

    def fake_import_module(name):
        def fake_search(query, limit, **kwargs):
            recorded[name] = (query, limit, kwargs)
            return [{"title": "Wiki", "url": "https://w", "snippet": "wiki"}]

        return SimpleNamespace(search=fake_search)

    monkeypatch.setattr(module.importlib, "import_module", fake_import_module)

    items = module._call_provider(module.PROVIDER_GROUPS["wikipedia"][0], "China", 3, "cs.CL", lang="zh")

    assert recorded["wikipedia_search"] == ("China", 3, {"lang": "zh"})
    assert items == [{"title": "Wiki", "url": "https://w", "snippet": "wiki"}]


def test_language_is_only_passed_to_supported_providers(monkeypatch):
    module = _load_module("search_academic_unified_search_lang_kwargs")
    recorded = {}

    def fake_import_module(name):
        def fake_search(query, limit, **kwargs):
            recorded[name] = kwargs
            return [{"title": name, "url": "", "snippet": ""}]

        return SimpleNamespace(search=fake_search)

    monkeypatch.setattr(module.importlib, "import_module", fake_import_module)

    module._call_provider(module.PROVIDER_GROUPS["google_scholar"][0], "q", 5, None, lang="zh")
    module._call_provider(module.PROVIDER_GROUPS["wikipedia"][0], "q", 5, None, lang="zh")
    module._call_provider(module.PROVIDER_GROUPS["pubmed"][0], "q", 5, None, lang="zh")

    assert recorded["google_scholar_search"] == {"lang": "zh"}
    assert recorded["wikipedia_search"] == {"lang": "zh"}
    assert recorded["pubmed_search"] == {}


def test_default_sources_and_deduplication(monkeypatch):
    module = _load_module("search_academic_unified_search_all")
    first_provider_by_source = {
        "arxiv": "arxiv_search",
        "semantic": "semantic_scholar_search",
        "google_scholar": "google_scholar_search",
        "pubmed": "pubmed_search",
        "wikipedia": "wikipedia_search",
    }
    calls = []

    def fake_call_provider(provider, query, limit, category, lang=None):
        calls.append(provider.module_name)
        assert query == "transformer"
        assert limit == 2
        if first_provider_by_source[provider.source] != provider.module_name:
            raise AssertionError(f"fallback should not run for {provider.source}")
        if provider.source == "arxiv":
            return [
                {"title": "Same", "url": "https://arxiv.org/abs/1", "snippet": "one", "arxiv_id": "1"},
                {"title": "Same duplicate", "url": "https://arxiv.org/abs/1", "snippet": "two", "arxiv_id": "1"},
            ]
        if provider.source == "semantic":
            return [{"title": "Semantic", "url": "https://s2/p", "abstract": "semantic", "paper_id": "p"}]
        if provider.source == "google_scholar":
            return [{"title": "Scholar", "url": "https://g", "snippet": "scholar", "citation_count": 3}]
        if provider.source == "pubmed":
            return [{"title": "PubMed", "url": "https://p", "snippet": "pubmed", "pmid": "123"}]
        return [{"title": "Wiki", "url": "https://w", "snippet": "wiki", "page_id": 9}]

    monkeypatch.setattr(module, "_call_provider", fake_call_provider)

    result = module.search("transformer", limit=2)

    assert set(calls) == set(first_provider_by_source.values())
    assert len(calls) == len(first_provider_by_source)
    assert result["sources"] == ["arxiv", "semantic", "google_scholar", "pubmed", "wikipedia"]
    assert [(item["source"], item["provider"], item["title"]) for item in result["items"]] == [
        ("arxiv", "arxiv_official", "Same"),
        ("semantic", "semantic_scholar_official", "Semantic"),
        ("google_scholar", "google_scholar", "Scholar"),
        ("pubmed", "pubmed", "PubMed"),
        ("wikipedia", "wikipedia", "Wiki"),
    ]


def test_output_normalization_removes_only_top_level_items():
    module = _load_module("search_academic_unified_search_output_normalization")
    result = {
        "success": True,
        "query": "q",
        "provider": "search.py",
        "sources": ["pubmed"],
        "items": [{"title": "top-level"}],
        "source_results": [
            {
                "source": "pubmed",
                "items": [{"title": "nested"}],
                "success": True,
            }
        ],
        "error": None,
    }

    normalized = module._normalize_output_result(result)

    assert "items" not in normalized
    assert normalized["source_results"][0]["items"] == [{"title": "nested"}]
    assert result["items"] == [{"title": "top-level"}]


def test_search_runs_sources_concurrently_and_preserves_output_order(monkeypatch):
    module = _load_module("search_academic_unified_search_concurrent_sources")
    started: list[str] = []
    lock = threading.Lock()
    both_started = threading.Event()

    def fake_search_source(source, query, limit, category, provider_timeout, lang):
        assert query == "q"
        assert limit == 1
        assert provider_timeout == 7
        assert lang == "zh"
        with lock:
            started.append(source)
            if len(started) == 2:
                both_started.set()
        assert both_started.wait(1), "sources did not run concurrently"
        return {
            "source": source,
            "success": True,
            "provider": f"{source}_provider",
            "items": [{"source": source, "provider": f"{source}_provider", "title": source}],
            "attempts": [],
            "error": None,
        }

    monkeypatch.setattr(module, "_search_source", fake_search_source)

    result = module.search("q", sources=["arxiv", "semantic"], limit=1, provider_timeout=7, lang="zh")

    assert set(started) == {"arxiv", "semantic"}
    assert [source_result["source"] for source_result in result["source_results"]] == ["arxiv", "semantic"]
    assert [item["source"] for item in result["items"]] == ["arxiv", "semantic"]


def test_search_uses_default_provider_timeout(monkeypatch):
    module = _load_module("search_academic_unified_search_default_timeout")
    seen_timeouts = []

    def fake_search_source(source, query, limit, category, provider_timeout, lang):
        seen_timeouts.append(provider_timeout)
        return {
            "source": source,
            "success": True,
            "provider": "pubmed",
            "items": [],
            "attempts": [],
            "error": None,
        }

    monkeypatch.setattr(module, "_search_source", fake_search_source)

    module.search("q", sources=["pubmed"], limit=1)

    assert seen_timeouts == [60]


def test_provider_call_times_out(monkeypatch):
    module = _load_module("search_academic_unified_search_provider_timeout")

    def slow_call_provider(provider, query, limit, category, lang=None):
        time.sleep(0.2)
        return [{"title": "late", "url": "", "snippet": ""}]

    monkeypatch.setattr(module, "_call_provider", slow_call_provider)

    started_at = time.perf_counter()
    with pytest.raises(TimeoutError, match="timed out after 0.01s"):
        module._call_provider_with_timeout(
            module.PROVIDER_GROUPS["pubmed"][0],
            "q",
            1,
            None,
            timeout_seconds=0.01,
        )

    assert time.perf_counter() - started_at < 0.15


def test_cli_outputs_unified_json(monkeypatch, capsys):
    module = _load_module("search_academic_unified_search_cli")

    monkeypatch.setattr(
        module,
        "search",
        lambda query, sources=None, limit=10, category=None, provider_timeout=60, lang=None: {
            "success": True,
            "query": query,
            "provider": "search.py",
            "sources": sources,
            "items": [{"title": "ok", "source": sources[0]}],
            "error": None,
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["search.py", "NSA", "--source", "arxiv,semantic", "--limit", "4", "--category", "cs.CL"],
    )

    module.main()

    output = json.loads(capsys.readouterr().out)
    assert output == {
        "success": True,
        "query": "NSA",
        "provider": "search.py",
        "sources": ["arxiv", "semantic"],
        "error": None,
    }


def test_cli_writes_json_output_file(monkeypatch, capsys, tmp_path):
    module = _load_module("search_academic_unified_search_output")
    output_path = tmp_path / "nested" / "result.json"

    monkeypatch.setattr(
        module,
        "search",
        lambda query, sources=None, limit=10, category=None, provider_timeout=60, lang=None: {
            "success": True,
            "query": query,
            "provider": "search.py",
            "sources": sources,
            "items": [{"title": "ok", "source": sources[0]}],
            "error": None,
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["search.py", "NSA", "--source", "pubmed", "--output", str(output_path)],
    )

    module.main()

    stdout_json = json.loads(capsys.readouterr().out)
    file_json = json.loads(output_path.read_text(encoding="utf-8"))
    expected = {
        "success": True,
        "query": "NSA",
        "provider": "search.py",
        "sources": ["pubmed"],
        "error": None,
        "output_path": str(output_path.resolve()),
    }
    assert stdout_json == expected
    assert file_json == expected


def test_cli_passes_provider_timeout(monkeypatch, capsys):
    module = _load_module("search_academic_unified_search_cli_timeout")
    seen = {}

    def fake_search(query, sources=None, limit=10, category=None, provider_timeout=60, lang=None):
        seen["provider_timeout"] = provider_timeout
        return {
            "success": True,
            "query": query,
            "provider": "search.py",
            "sources": sources,
            "items": [],
            "error": None,
        }

    monkeypatch.setattr(module, "search", fake_search)
    monkeypatch.setattr(sys, "argv", ["search.py", "NSA", "--source", "pubmed", "--provider-timeout", "12.5"])

    module.main()

    assert seen == {"provider_timeout": 12.5}
    assert json.loads(capsys.readouterr().out)["success"] is True


def test_cli_passes_lang(monkeypatch, capsys):
    module = _load_module("search_academic_unified_search_cli_lang")
    seen = {}

    def fake_search(query, sources=None, limit=10, category=None, provider_timeout=60, lang=None):
        seen["lang"] = lang
        return {
            "success": True,
            "query": query,
            "provider": "search.py",
            "sources": sources,
            "items": [],
            "error": None,
        }

    monkeypatch.setattr(module, "search", fake_search)
    monkeypatch.setattr(sys, "argv", ["search.py", "中国", "--source", "wikipedia", "--lang", "zh"])

    module.main()

    assert seen == {"lang": "zh"}
    assert json.loads(capsys.readouterr().out)["success"] is True
