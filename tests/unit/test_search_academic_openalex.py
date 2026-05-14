import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / ".sensenova-claw"
    / "skills"
    / "search-academic"
    / "scripts"
    / "openalex_search.py"
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


def _load_module(name="search_academic_openalex"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_openalex_search_normalizes_work_fields(monkeypatch):
    module = _load_module("search_academic_openalex_normalize")
    client = _FakeClient(
        [
            _FakeResponse(
                {
                    "results": [
                        {
                            "id": "https://openalex.org/W2741809807",
                            "doi": "https://doi.org/10.48550/arxiv.1706.03762",
                            "title": "Attention Is All You Need",
                            "display_name": "Attention Is All You Need",
                            "publication_year": 2017,
                            "publication_date": "2017-06-12",
                            "cited_by_count": 120000,
                            "type": "article",
                            "open_access": {
                                "is_oa": True,
                                "oa_url": "https://example.test/paper.pdf",
                            },
                            "primary_location": {
                                "landing_page_url": "https://example.test/paper",
                                "pdf_url": "https://example.test/paper.pdf",
                                "source": {
                                    "display_name": "Advances in Neural Information Processing Systems",
                                    "type": "conference",
                                },
                            },
                            "authorships": [
                                {"author": {"display_name": "Ashish Vaswani"}},
                                {"author": {"display_name": "Noam Shazeer"}},
                            ],
                            "concepts": [
                                {"display_name": "Computer science", "score": 0.92},
                                {"display_name": "Machine learning", "score": 0.81},
                            ],
                            "abstract_inverted_index": {
                                "The": [0],
                                "dominant": [1],
                                "models": [2],
                            },
                        }
                    ]
                }
            )
        ]
    )

    monkeypatch.setattr(module, "get_client", lambda **kwargs: client)

    items = module.search(
        "attention",
        limit=1,
        api_key="openalex-key",
        mailto="bot@example.test",
    )

    assert client.calls == [
        (
            "https://api.openalex.org/works",
            {
                "search": "attention",
                "per-page": "1",
                "sort": "relevance_score:desc",
                "select": module.SELECT_FIELDS,
                "api_key": "openalex-key",
                "mailto": "bot@example.test",
            },
        )
    ]
    assert items == [
        {
            "title": "Attention Is All You Need",
            "url": "https://example.test/paper",
            "snippet": "The dominant models",
            "authors": ["Ashish Vaswani", "Noam Shazeer"],
            "year": 2017,
            "publication_date": "2017-06-12",
            "venue": "Advances in Neural Information Processing Systems",
            "source_type": "conference",
            "citation_count": 120000,
            "is_open_access": True,
            "open_access_url": "https://example.test/paper.pdf",
            "pdf_url": "https://example.test/paper.pdf",
            "doi": "10.48550/arxiv.1706.03762",
            "openalex_id": "W2741809807",
            "work_type": "article",
            "concepts": ["Computer science", "Machine learning"],
        }
    ]


def test_openalex_search_supports_year_filters(monkeypatch):
    module = _load_module("search_academic_openalex_filters")
    client = _FakeClient([_FakeResponse({"results": []})])

    monkeypatch.setattr(module, "get_client", lambda **kwargs: client)

    items = module.search("diffusion", limit=5, year_min=2020, year_max=2024)

    assert items == []
    assert client.calls[0][1]["filter"] == "from_publication_date:2020-01-01,to_publication_date:2024-12-31"
