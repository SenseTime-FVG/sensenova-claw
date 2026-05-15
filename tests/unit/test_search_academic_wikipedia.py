import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / ".sensenova-claw"
    / "skills"
    / "search-academic"
    / "scripts"
    / "wikipedia_search.py"
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


def _load_module(name="search_academic_wikipedia"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_wikipedia_search_uses_descriptive_user_agent(monkeypatch):
    module = _load_module("search_academic_wikipedia_headers")
    client = _FakeClient([_FakeResponse({"query": {"search": []}})])
    captured_kwargs = {}

    def fake_get_client(**kwargs):
        captured_kwargs.update(kwargs)
        return client

    monkeypatch.setattr(module, "get_client", fake_get_client)

    assert module.search("China", limit=1) == []

    assert "headers" in captured_kwargs
    user_agent = captured_kwargs["headers"]["User-Agent"]
    assert "sensenova-claw" in user_agent
    assert "search-academic" in user_agent
    assert "github.com/SenseTime-FVG/sensenova-claw" in user_agent
    assert "Mozilla" not in user_agent
