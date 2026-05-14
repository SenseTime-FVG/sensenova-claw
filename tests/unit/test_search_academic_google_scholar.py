import importlib.util
from pathlib import Path
from types import SimpleNamespace


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / ".sensenova-claw"
    / "skills"
    / "search-academic"
    / "scripts"
    / "google_scholar_search.py"
)


HTML = """
<html>
  <body>
    <div class="gs_r gs_or gs_scl" data-cid="1234567890">
      <div class="gs_ggs gs_fl">
        <div class="gs_or_ggsm"><a href="https://example.test/paper.pdf">[PDF] example.test</a></div>
      </div>
      <div class="gs_ri">
        <h3 class="gs_rt"><a href="https://example.test/paper">Attention is all you need</a></h3>
        <div class="gs_a">A Vaswani, N Shazeer - Advances in neural information processing systems, 2017 - example.test</div>
        <div class="gs_rs">The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.</div>
        <div class="gs_fl">
          <a href="/scholar?cites=1234567890">Cited by 120000</a>
          <a href="/scholar?q=related:1234567890">Related articles</a>
          <a href="/scholar?cluster=1234567890">All 42 versions</a>
        </div>
      </div>
    </div>
    <div class="gs_r gs_or gs_scl" data-cid="9876543210">
      <div class="gs_ri">
        <h3 class="gs_rt">[CITATION] A title without a landing page</h3>
        <div class="gs_a">J Doe - 2024</div>
        <div class="gs_rs"></div>
      </div>
    </div>
  </body>
</html>
"""


CAPTCHA_HTML = """
<html><body><form id="gs_captcha_f"><input name="captcha"/></form></body></html>
"""


class _FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code
        self.headers = {"content-type": "text/html; charset=utf-8"}

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


def _load_module(name="search_academic_google_scholar"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_google_scholar_result_html():
    module = _load_module("search_academic_google_scholar_parse")

    items = module.parse_results(HTML)

    assert items[0] == {
        "title": "Attention is all you need",
        "url": "https://example.test/paper",
        "snippet": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.",
        "authors": ["A Vaswani", "N Shazeer"],
        "year": 2017,
        "venue": "Advances in neural information processing systems",
        "pdf_url": "https://example.test/paper.pdf",
        "citation_count": 120000,
        "cited_by_url": "https://scholar.google.com/scholar?cites=1234567890",
        "related_url": "https://scholar.google.com/scholar?q=related:1234567890",
        "versions_url": "https://scholar.google.com/scholar?cluster=1234567890",
        "scholar_id": "1234567890",
    }
    assert items[1]["title"] == "A title without a landing page"
    assert items[1]["url"] == ""
    assert items[1]["year"] == 2024


def test_search_paginates_and_sends_year_filters(monkeypatch):
    module = _load_module("search_academic_google_scholar_search")
    client = _FakeClient([_FakeResponse(HTML), _FakeResponse(HTML)])

    monkeypatch.setattr(module, "get_client", lambda **kwargs: client)
    monkeypatch.setattr(module, "time", SimpleNamespace(sleep=lambda delay: None), raising=False)

    items = module.search("transformer", limit=3, year_min=2017, year_max=2024, sleep_seconds=0)

    assert len(items) == 3
    assert client.calls[0][1]["q"] == "transformer"
    assert client.calls[0][1]["as_ylo"] == "2017"
    assert client.calls[0][1]["as_yhi"] == "2024"
    assert client.calls[0][1]["start"] == "0"
    assert client.calls[1][1]["start"] == "10"


def test_captcha_page_is_reported_as_blocked(monkeypatch):
    module = _load_module("search_academic_google_scholar_blocked")
    client = _FakeClient([_FakeResponse(CAPTCHA_HTML)])

    monkeypatch.setattr(module, "get_client", lambda **kwargs: client)

    try:
        module.search("transformer", limit=1)
    except module.GoogleScholarBlockedError as exc:
        assert "验证码" in str(exc)
    else:
        raise AssertionError("expected GoogleScholarBlockedError")
