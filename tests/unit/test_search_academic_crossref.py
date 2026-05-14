import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / ".sensenova-claw"
    / "skills"
    / "search-academic"
    / "scripts"
    / "crossref_search.py"
)


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
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


def _load_module(name="search_academic_crossref"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_crossref_search_normalizes_work_fields(monkeypatch):
    module = _load_module("search_academic_crossref_normalize")
    client = _FakeClient(
        [
            _FakeResponse(
                {
                    "message": {
                        "items": [
                            {
                                "DOI": "10.5555/example",
                                "URL": "https://doi.org/10.5555/example",
                                "title": ["An example paper"],
                                "abstract": "<jats:p>This is an abstract.</jats:p>",
                                "author": [
                                    {"given": "Ada", "family": "Lovelace"},
                                    {"name": "Example Consortium"},
                                ],
                                "published-print": {"date-parts": [[2024, 3, 5]]},
                                "container-title": ["Journal of Examples"],
                                "publisher": "Example Press",
                                "type": "journal-article",
                                "is-referenced-by-count": 42,
                                "ISSN": ["1234-5678"],
                                "subject": ["Computer science"],
                                "link": [
                                    {
                                        "URL": "https://example.test/paper.pdf",
                                        "content-type": "application/pdf",
                                    }
                                ],
                            }
                        ]
                    }
                }
            )
        ]
    )

    monkeypatch.setattr(module, "get_client", lambda **kwargs: client)

    items = module.search(
        "example",
        limit=1,
        mailto="bot@example.test",
        year_min=2020,
        year_max=2024,
    )

    assert client.calls == [
        (
            "https://api.crossref.org/works",
            {
                "query": "example",
                "rows": "1",
                "sort": "relevance",
                "order": "desc",
                "mailto": "bot@example.test",
                "filter": "from-pub-date:2020-01-01,until-pub-date:2024-12-31",
            },
        )
    ]
    assert items == [
        {
            "title": "An example paper",
            "url": "https://doi.org/10.5555/example",
            "snippet": "This is an abstract.",
            "authors": ["Ada Lovelace", "Example Consortium"],
            "year": 2024,
            "publication_date": "2024-03-05",
            "venue": "Journal of Examples",
            "publisher": "Example Press",
            "work_type": "journal-article",
            "citation_count": 42,
            "doi": "10.5555/example",
            "issn": ["1234-5678"],
            "subjects": ["Computer science"],
            "pdf_url": "https://example.test/paper.pdf",
        }
    ]


def test_crossref_search_uses_created_date_fallback(monkeypatch):
    module = _load_module("search_academic_crossref_created")
    client = _FakeClient(
        [
            _FakeResponse(
                {
                    "message": {
                        "items": [
                            {
                                "DOI": "10.5555/no-pub-date",
                                "title": ["No publication date"],
                                "created": {"date-parts": [[2019, 1, 2]]},
                            }
                        ]
                    }
                }
            )
        ]
    )

    monkeypatch.setattr(module, "get_client", lambda **kwargs: client)

    items = module.search("fallback", limit=5)

    assert items[0]["year"] == 2019
    assert items[0]["publication_date"] == "2019-01-02"
