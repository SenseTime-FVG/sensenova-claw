import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / ".sensenova-claw"
    / "skills"
    / "search-academic"
    / "scripts"
    / "arxiv_search.py"
)


class _FakeSortCriterion:
    Relevance = "relevance"
    SubmittedDate = "submitted"


class _FakeSearch:
    def __init__(self, query=None, id_list=None, max_results=10, sort_by=None):
        self.query = query
        self.id_list = id_list
        self.max_results = max_results
        self.sort_by = sort_by


class _FakeClient:
    last_search = None
    download_calls = []

    def results(self, search):
        type(self).last_search = search
        class Author:
            def __init__(self, name):
                self.name = name

            def __str__(self):
                return self.name

        return iter(
            [
                SimpleNamespace(
                    entry_id="https://arxiv.org/abs/2401.12345v2",
                    title="  A Useful Paper\nfor Tests ",
                    authors=[Author("Ada Lovelace"), Author("Alan Turing")],
                    published=datetime(2024, 1, 2, tzinfo=timezone.utc),
                    updated=datetime(2024, 2, 3, tzinfo=timezone.utc),
                    categories=["cs.CL", "cs.AI"],
                    primary_category="cs.CL",
                    pdf_url="https://arxiv.org/pdf/2401.12345v2",
                    summary="Abstract body",
                    comment="12 pages",
                    journal_ref="Test Journal",
                    doi="10.1234/test",
                    links=[SimpleNamespace(href="https://arxiv.org/abs/2401.12345v2", title=None)],
                    download_pdf=self._download_pdf,
                )
            ]
        )

    def _download_pdf(self, dirpath, filename):
        self.download_calls.append((dirpath, filename))


def _load_module(monkeypatch):
    _FakeClient.last_search = None
    _FakeClient.download_calls = []
    fake_arxiv = ModuleType("arxiv")
    fake_arxiv.Client = _FakeClient
    fake_arxiv.Search = _FakeSearch
    fake_arxiv.SortCriterion = _FakeSortCriterion
    monkeypatch.setitem(sys.modules, "arxiv", fake_arxiv)

    spec = importlib.util.spec_from_file_location("search_academic_arxiv_search", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_search_uses_arxiv_package_and_keeps_legacy_item_fields(monkeypatch):
    module = _load_module(monkeypatch)

    items = module.search("transformer", limit=1, sort_by="date")

    assert _FakeClient.last_search.query == "all:transformer"
    assert _FakeClient.last_search.max_results == 1
    assert _FakeClient.last_search.sort_by == _FakeSortCriterion.SubmittedDate
    assert items == [
        {
            "title": "A Useful Paper for Tests",
            "url": "https://arxiv.org/abs/2401.12345v2",
            "snippet": "Abstract body",
            "arxiv_id": "2401.12345v2",
            "authors": ["Ada Lovelace", "Alan Turing"],
            "published": "2024-01-02T00:00:00+00:00",
            "updated": "2024-02-03T00:00:00+00:00",
            "pdf_url": "https://arxiv.org/pdf/2401.12345v2",
            "html_url": "https://arxiv.org/html/2401.12345v2",
            "categories": ["cs.CL", "cs.AI"],
            "primary_category": "cs.CL",
            "comment": "12 pages",
            "journal_ref": "Test Journal",
            "doi": "10.1234/test",
        }
    ]


def test_fetch_by_ids_cleans_prefixes(monkeypatch):
    module = _load_module(monkeypatch)

    module.fetch_by_ids(["arXiv:2401.12345", " 2301.00001 "], limit=2)

    assert _FakeClient.last_search.id_list == ["2401.12345", "2301.00001"]


def test_search_does_not_prefix_existing_arxiv_field_query(monkeypatch):
    module = _load_module(monkeypatch)

    module.search("all:PixArt-alpha AND cat:cs.CV", limit=1)

    assert _FakeClient.last_search.query == "all:PixArt-alpha AND cat:cs.CV"


def test_download_pdf_uses_arxiv_package_and_returns_path(monkeypatch, tmp_path):
    module = _load_module(monkeypatch)

    filepath = module.download_pdf("arXiv:2401.12345", str(tmp_path))

    assert _FakeClient.last_search.id_list == ["2401.12345"]
    assert _FakeClient.download_calls == [(str(tmp_path), "2401.12345.pdf")]
    assert filepath == str(tmp_path / "2401.12345.pdf")


def test_hidden_download_cli_outputs_json_but_help_does_not_mention_it(monkeypatch, tmp_path, capsys):
    module = _load_module(monkeypatch)

    monkeypatch.setattr(sys, "argv", ["arxiv_search.py", "--help"])
    try:
        module.main()
    except SystemExit:
        pass
    help_output = capsys.readouterr().out
    assert "download" not in help_output

    monkeypatch.setattr(
        sys,
        "argv",
        ["arxiv_search.py", "download", "arXiv:2401.12345", "--output", str(tmp_path)],
    )
    module.main()

    output = json.loads(capsys.readouterr().out)
    assert output == {
        "success": True,
        "arxiv_id": "2401.12345",
        "output_path": str(tmp_path / "2401.12345.pdf"),
        "error": None,
    }
