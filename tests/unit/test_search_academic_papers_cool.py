import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / ".sensenova-claw"
    / "skills"
    / "search-academic"
    / "scripts"
    / "arxiv_mirror_search.py"
)


HTML = """
<html>
  <body id="arxiv">
    <h1 class="notranslate">transformer</h1>
    <p class="info notranslate">
      <a class="date">2026-05-13</a> | Total: 1000
    </p>
    <div class="papers">
      <div id="2307.01189" class="panel paper" keywords="tint,transformer,language">
        <h2 class="title">
          <a href="https://arxiv.org/abs/2307.01189" target="_blank" title="1/1000"><span class="index notranslate">#1</span></a>
          <a id="title-2307.01189" class="title-link notranslate" href="/arxiv/2307.01189" target="_blank">Trainable Transformer in Transformer</a>
          <a id="pdf-2307.01189" class="title-pdf notranslate" data="https://arxiv.org/pdf/2307.01189">[PDF<sup>20</sup>]</a>
        </h2>
        <p id="authors-2307.01189" class="metainfo authors notranslate"><strong>Authors</strong>:
          <a class="author notranslate" href="https://arxiv.org/search/?searchtype=author&amp;query=Abhishek Panigrahi">Abhishek Panigrahi</a>,
          <a class="author notranslate" href="https://arxiv.org/search/?searchtype=author&amp;query=Sadhika Malladi">Sadhika Malladi</a>
        </p>
        <p id="summary-2307.01189" class="summary notranslate">Recent works attribute the capability of in-context learning to internal fine-tuning.</p>
        <p id="subjects-2307.01189" class="metainfo subjects"><strong>Subjects</strong>:
          <span><a class="subject-1" href="/arxiv/cs.CL">Computation and Language</a></span>,
          <span><a class="subject-2" href="/arxiv/cs.LG">Machine Learning</a></span>
        </p>
        <p id="date-2307.01189" class="metainfo date"><strong>Publish</strong>: <span class="date-data">2023-07-03 17:53:39 UTC</span></p>
      </div>
    </div>
  </body>
</html>
"""


class _FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"unexpected HTTP error {self.status_code}")


class _FakeClient:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, params=None):
        self.calls.append((url, params))
        return _FakeResponse(HTML)


def _load_module(name="search_academic_papers_cool"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_papers_cool_arxiv_html():
    module = _load_module("search_academic_papers_cool_parse")

    items = module.parse_results(HTML)

    assert items == [
        {
            "title": "Trainable Transformer in Transformer",
            "url": "https://papers.cool/arxiv/2307.01189",
            "snippet": "Recent works attribute the capability of in-context learning to internal fine-tuning.",
            "arxiv_id": "2307.01189",
            "authors": ["Abhishek Panigrahi", "Sadhika Malladi"],
            "published": "2023-07-03 17:53:39 UTC",
            "pdf_url": "https://arxiv.org/pdf/2307.01189",
            "abs_url": "https://arxiv.org/abs/2307.01189",
            "html_url": "https://arxiv.org/html/2307.01189",
            "mirror_url": "https://papers.cool/arxiv/2307.01189",
            "categories": ["cs.CL", "cs.LG"],
            "subjects": ["Computation and Language", "Machine Learning"],
            "keywords": ["tint", "transformer", "language"],
        }
    ]


def test_search_uses_papers_cool_arxiv_search_endpoint(monkeypatch):
    module = _load_module("search_academic_papers_cool_search")
    client = _FakeClient()

    monkeypatch.setattr(module, "get_client", lambda **kwargs: client)

    items = module.search("large language model", limit=1)

    assert len(items) == 1
    assert client.calls == [
        (
            "https://papers.cool/arxiv/search",
            {"query": "large language model", "highlight": "1"},
        )
    ]


def test_category_search_supports_date(monkeypatch):
    module = _load_module("search_academic_papers_cool_category")
    client = _FakeClient()

    monkeypatch.setattr(module, "get_client", lambda **kwargs: client)

    module.search("ignored", limit=1, category="cs.CL", date="2026-05-13")

    assert client.calls == [
        (
            "https://papers.cool/arxiv/cs.CL",
            {"date": "2026-05-13"},
        )
    ]
