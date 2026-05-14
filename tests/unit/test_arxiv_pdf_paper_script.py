import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / ".sensenova-claw"
    / "skills"
    / "search-academic"
    / "scripts"
    / "arxiv_pdf_paper.py"
)


class _FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"unexpected HTTP error {self.status_code}")


class _FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url):
        self.calls.append(url)
        return self.response


def load_module():
    spec = importlib.util.spec_from_file_location("arxiv_pdf_paper", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_cmd_read_pdf_fetches_arxiv_pdf_and_extracts_full_text(monkeypatch):
    module = load_module()
    client = _FakeClient(_FakeResponse(b"%PDF fake bytes"))

    class FakePage:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    class FakePdfReader:
        def __init__(self, stream):
            assert stream.read() == b"%PDF fake bytes"
            self.pages = [
                FakePage("Title\n\nFirst page text."),
                FakePage("Second page text."),
            ]

    monkeypatch.setattr(module, "get_client", lambda **kwargs: client)
    monkeypatch.setattr(module, "_load_pdf_reader", lambda: FakePdfReader)

    result = module.cmd_read_pdf("https://arxiv.org/pdf/2309.16609")

    assert client.calls == ["https://arxiv.org/pdf/2309.16609"]
    assert result == {
        "success": True,
        "arxiv_id": "2309.16609",
        "abs_url": "https://arxiv.org/abs/2309.16609",
        "pdf_url": "https://arxiv.org/pdf/2309.16609",
        "content": "Title\n\nFirst page text.\n\nSecond page text.",
        "char_count": 42,
        "page_count": 2,
        "error": None,
    }


def test_normalize_arxiv_id_accepts_common_inputs():
    module = load_module()

    assert module.normalize_arxiv_id("arXiv:2309.16609v2") == "2309.16609v2"
    assert module.normalize_arxiv_id("https://arxiv.org/pdf/2309.16609") == "2309.16609"
    assert module.normalize_arxiv_id("https://arxiv.org/abs/2309.16609v1") == "2309.16609v1"


def test_extract_with_python_pdftotext_package(monkeypatch):
    module = load_module()

    class FakePdf:
        def __init__(self, stream):
            assert stream.read() == b"%PDF fake bytes"

        def __iter__(self):
            return iter(["Page one text.", "Page two text."])

    monkeypatch.setattr(module, "_load_pdftotext_pdf", lambda: FakePdf)

    content, page_count = module._extract_with_python_pdftotext(b"%PDF fake bytes")

    assert content == "Page one text.\n\nPage two text."
    assert page_count == 2
