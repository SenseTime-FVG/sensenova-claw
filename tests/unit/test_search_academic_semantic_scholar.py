import importlib.util
from pathlib import Path
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

    monkeypatch.setattr(module, "get_client", lambda **kwargs: client)
    monkeypatch.setattr(module, "time", SimpleNamespace(sleep=lambda delay: None), raising=False)

    items = module.search("Scalable Diffusion Models with Transformers", limit=1)

    assert len(client.calls) == 2
    assert items[0]["title"] == "Scalable Diffusion Models with Transformers"
    assert items[0]["citation_count"] == 42


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
