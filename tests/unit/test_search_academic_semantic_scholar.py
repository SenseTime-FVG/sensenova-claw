import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace


SEARCH_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / ".sensenova-claw"
    / "skills"
    / "search-academic"
    / "scripts"
    / "semantic_scholar_search.py"
)

REFS_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / ".sensenova-claw"
    / "skills"
    / "search-academic"
    / "scripts"
    / "semantic_scholar_refs.py"
)


class _FakeResponse:
    def __init__(self, status_code, payload, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.raise_calls = 0

    def json(self):
        return self._payload

    def raise_for_status(self):
        self.raise_calls += 1
        if self.status_code >= 400:
            raise AssertionError(f"unexpected HTTP error {self.status_code}")


class _FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, params=None):
        self.calls.append((url, params))
        return self.responses.pop(0)


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_semantic_scholar_search_uses_sdk_before_http(monkeypatch):
    class _FakeSemanticScholar:
        calls = []

        def __init__(self, *args, **kwargs):
            self.calls.append(("init", args, kwargs))

        def search_paper(self, query, *, limit):
            self.calls.append(("search_paper", query, limit))
            return [SimpleNamespace(paperId="paper-1")]

        def get_paper(self, paper_id, *, fields):
            self.calls.append(("get_paper", paper_id, fields))
            assert "tldr" in fields
            assert "referenceCount" in fields
            return SimpleNamespace(
                title="SDK Paper",
                abstract="SDK abstract",
                tldr=SimpleNamespace(text="SDK TLDR"),
                year=2024,
                venue="SDK Venue",
                publicationDate=datetime(2024, 1, 2),
                authors=[SimpleNamespace(name="Ada Lovelace")],
                citationCount=12,
                influentialCitationCount=3,
                referenceCount=4,
                isOpenAccess=True,
                openAccessPdf={"url": "https://example.test/sdk.pdf"},
                externalIds={"DOI": "10.1234/sdk", "ArXiv": "2401.00001"},
                fieldsOfStudy=["Computer Science"],
                publicationTypes=["JournalArticle"],
                paperId=paper_id,
                url="https://www.semanticscholar.org/paper/paper-1",
            )

    fake_semanticscholar = ModuleType("semanticscholar")
    fake_semanticscholar.SemanticScholar = _FakeSemanticScholar
    monkeypatch.setitem(sys.modules, "semanticscholar", fake_semanticscholar)

    module = _load_module(SEARCH_SCRIPT_PATH, "search_academic_semantic_scholar_search_sdk")
    monkeypatch.setattr(
        module,
        "get_client",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("HTTP fallback should not run")),
    )

    items = module.search("SDK query", limit=1, api_key="sdk-key")

    assert _FakeSemanticScholar.calls[:2] == [
        ("init", (), {"api_key": "sdk-key"}),
        ("search_paper", "SDK query", 1),
    ]
    assert items == [
        {
            "title": "SDK Paper",
            "url": "https://www.semanticscholar.org/paper/paper-1",
            "snippet": "SDK abstract",
            "tldr": "SDK TLDR",
            "authors": ["Ada Lovelace"],
            "year": 2024,
            "venue": "SDK Venue",
            "publication_date": "2024-01-02",
            "citation_count": 12,
            "influential_citation_count": 3,
            "reference_count": 4,
            "is_open_access": True,
            "open_access_pdf": "https://example.test/sdk.pdf",
            "fields_of_study": ["Computer Science"],
            "publication_types": ["JournalArticle"],
            "doi": "10.1234/sdk",
            "arxiv_id": "2401.00001",
            "paper_id": "paper-1",
        }
    ]


def test_semantic_scholar_search_falls_back_to_http_when_sdk_fails(monkeypatch):
    class _FailingSemanticScholar:
        def __init__(self, *args, **kwargs):
            pass

        def search_paper(self, query, *, limit):
            raise RuntimeError("SDK unavailable")

    fake_semanticscholar = ModuleType("semanticscholar")
    fake_semanticscholar.SemanticScholar = _FailingSemanticScholar
    monkeypatch.setitem(sys.modules, "semanticscholar", fake_semanticscholar)

    module = _load_module(SEARCH_SCRIPT_PATH, "search_academic_semantic_scholar_search_fallback")
    client = _FakeClient(
        [
            _FakeResponse(
                200,
                {
                    "data": [
                        {
                            "title": "HTTP Paper",
                            "paperId": "paper-http",
                            "authors": [{"name": "Grace Hopper"}],
                            "citationCount": 5,
                        }
                    ]
                },
            ),
        ]
    )

    monkeypatch.setattr(module, "get_client", lambda **kwargs: client)

    items = module.search("fallback query", limit=1)

    assert len(client.calls) == 1
    assert items[0]["title"] == "HTTP Paper"
    assert items[0]["paper_id"] == "paper-http"


def test_semantic_scholar_search_retries_429(monkeypatch):
    module = _load_module(SEARCH_SCRIPT_PATH, "search_academic_semantic_scholar_search")
    client = _FakeClient(
        [
            _FakeResponse(429, {}, {"Retry-After": "0"}),
            _FakeResponse(
                200,
                {
                    "data": [
                        {
                            "title": "Scalable Diffusion Models with Transformers",
                            "paperId": "paper-1",
                            "authors": [{"name": "William Peebles"}],
                            "citationCount": 42,
                        }
                    ]
                },
            ),
        ]
    )

    monkeypatch.setattr(module, "SemanticScholar", None)
    monkeypatch.setattr(module, "get_client", lambda **kwargs: client)
    monkeypatch.setattr(module, "time", SimpleNamespace(sleep=lambda delay: None), raising=False)

    items = module.search("Scalable Diffusion Models with Transformers", limit=1)

    assert len(client.calls) == 2
    assert items[0]["title"] == "Scalable Diffusion Models with Transformers"
    assert items[0]["citation_count"] == 42


def test_semantic_scholar_refs_uses_sdk_before_http(monkeypatch):
    class _FakeSemanticScholar:
        calls = []

        def __init__(self, *args, **kwargs):
            self.calls.append(("init", args, kwargs))

        def get_paper_citations(self, paper_id, *, fields, limit):
            self.calls.append(("get_paper_citations", paper_id, fields, limit))
            assert "contexts" in fields
            assert "intents" in fields
            assert "title" in fields
            assert limit == 1000
            return SimpleNamespace(
                items=[
                    SimpleNamespace(
                        paper=SimpleNamespace(
                            title="SDK Citing Paper",
                            paperId="paper-sdk",
                            abstract="SDK citing abstract",
                            authors=[SimpleNamespace(name="Grace Hopper")],
                            year=2024,
                            venue="SDK Conference",
                            publicationDate=datetime(2024, 2, 3),
                            citationCount=12,
                            influentialCitationCount=4,
                            isOpenAccess=True,
                            openAccessPdf={"url": "https://example.test/ref.pdf"},
                            fieldsOfStudy=["Computer Science"],
                            externalIds={"DOI": "10.1234/ref", "ArXiv": "2402.00001"},
                        ),
                        contexts=["context 1", "context 2", "context 3", "context 4"],
                        intents=["background"],
                    ),
                    SimpleNamespace(
                        paper=SimpleNamespace(
                            title="Filtered Low Citation",
                            paperId="paper-low",
                            year=2024,
                            citationCount=1,
                        ),
                        contexts=[],
                        intents=[],
                    ),
                ]
            )

        def get_paper(self, paper_id, *, fields):
            self.calls.append(("get_paper", paper_id, fields))
            return SimpleNamespace(title="SDK Source Paper", year=2023, citationCount=99)

    fake_semanticscholar = ModuleType("semanticscholar")
    fake_semanticscholar.SemanticScholar = _FakeSemanticScholar
    monkeypatch.setitem(sys.modules, "semanticscholar", fake_semanticscholar)

    module = _load_module(REFS_SCRIPT_PATH, "search_academic_semantic_scholar_refs_sdk")
    monkeypatch.setattr(
        module,
        "get_client",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("HTTP fallback should not run")),
    )

    result = module.fetch_refs(
        "paper-source",
        "citations",
        limit=1,
        min_citations=10,
        year_min=2020,
        year_max=2025,
        api_key="sdk-key",
    )

    assert _FakeSemanticScholar.calls[:2] == [
        ("init", (), {"api_key": "sdk-key"}),
        (
            "get_paper_citations",
            "paper-source",
            ["contexts", "intents", "title", "abstract", "year", "venue", "publicationDate", "authors", "citationCount", "influentialCitationCount", "isOpenAccess", "openAccessPdf", "externalIds", "fieldsOfStudy"],
            1000,
        ),
    ]
    assert result["source_paper"] == {
        "title": "SDK Source Paper",
        "year": 2023,
        "citation_count": 99,
    }
    assert result["items"] == [
        {
            "title": "SDK Citing Paper",
            "url": "https://www.semanticscholar.org/paper/paper-sdk",
            "snippet": "SDK citing abstract",
            "authors": ["Grace Hopper"],
            "year": 2024,
            "venue": "SDK Conference",
            "publication_date": "2024-02-03",
            "citation_count": 12,
            "influential_citation_count": 4,
            "is_open_access": True,
            "open_access_pdf": "https://example.test/ref.pdf",
            "fields_of_study": ["Computer Science"],
            "doi": "10.1234/ref",
            "arxiv_id": "2402.00001",
            "paper_id": "paper-sdk",
            "citation_contexts": ["context 1", "context 2", "context 3"],
            "citation_intents": ["background"],
        }
    ]


def test_semantic_scholar_refs_falls_back_to_http_when_sdk_fails(monkeypatch):
    class _FailingSemanticScholar:
        def __init__(self, *args, **kwargs):
            pass

        def get_paper_references(self, paper_id, *, fields, limit):
            raise RuntimeError("SDK unavailable")

    fake_semanticscholar = ModuleType("semanticscholar")
    fake_semanticscholar.SemanticScholar = _FailingSemanticScholar
    monkeypatch.setitem(sys.modules, "semanticscholar", fake_semanticscholar)

    module = _load_module(REFS_SCRIPT_PATH, "search_academic_semantic_scholar_refs_fallback")
    client = _FakeClient(
        [
            _FakeResponse(
                200,
                {
                    "data": [
                        {
                            "citedPaper": {
                                "title": "HTTP Referenced Paper",
                                "paperId": "paper-http",
                                "authors": [{"name": "Ada Lovelace"}],
                                "citationCount": 7,
                            }
                        }
                    ]
                },
            ),
            _FakeResponse(200, {"title": "HTTP Source Paper", "year": 2024, "citationCount": 10}),
        ]
    )

    monkeypatch.setattr(module, "get_client", lambda **kwargs: client)

    result = module.fetch_refs(
        "paper-source",
        "references",
        limit=1,
        min_citations=0,
        year_min=None,
        year_max=None,
    )

    assert len(client.calls) == 2
    assert client.calls[0][0].endswith("/paper/paper-source/references")
    assert result["items"][0]["title"] == "HTTP Referenced Paper"
    assert result["source_paper"]["title"] == "HTTP Source Paper"


def test_semantic_scholar_refs_retries_429(monkeypatch):
    module = _load_module(REFS_SCRIPT_PATH, "search_academic_semantic_scholar_refs")
    client = _FakeClient(
        [
            _FakeResponse(429, {}, {"Retry-After": "0"}),
            _FakeResponse(
                200,
                {
                    "data": [
                        {
                            "citedPaper": {
                                "title": "Referenced Paper",
                                "paperId": "paper-2",
                                "authors": [{"name": "Ada Lovelace"}],
                                "citationCount": 7,
                            }
                        }
                    ]
                },
            ),
            _FakeResponse(200, {"title": "Source Paper", "year": 2024, "citationCount": 10}),
        ]
    )

    monkeypatch.setattr(module, "SemanticScholar", None)
    monkeypatch.setattr(module, "get_client", lambda **kwargs: client)
    monkeypatch.setattr(module, "time", SimpleNamespace(sleep=lambda delay: None), raising=False)

    result = module.fetch_refs(
        "paper-1",
        "references",
        limit=1,
        min_citations=0,
        year_min=None,
        year_max=None,
    )

    assert len(client.calls) == 3
    assert result["items"][0]["title"] == "Referenced Paper"
    assert result["source_paper"]["title"] == "Source Paper"
