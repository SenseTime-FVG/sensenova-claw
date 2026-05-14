import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / ".sensenova-claw"
    / "skills"
    / "search-academic"
    / "scripts"
    / "deepxiv_paper.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("deepxiv_paper", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_cmd_list_sections_maps_deepxiv_head(monkeypatch):
    module = load_module()

    class FakeReader:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def head(self, arxiv_id):
            assert arxiv_id == "2308.15022"
            return {
                "title": "Recursive Memory",
                "abstract": "A memory paper.",
                "authors": [{"name": "Qingyue Wang"}, "Liang Ding"],
                "sections": [
                    {"name": "Abstract", "level": 0, "token_count": 30},
                    {"name": "1 Introduction", "level": 1, "token_count": 120},
                ],
                "token_count": 150,
                "categories": ["cs.AI", "cs.CL"],
                "publish_at": "2023-08-29T04:59:53Z",
            }

    monkeypatch.setattr(module, "Reader", FakeReader)
    result = module.cmd_list_sections("2308.15022", token="test-token")

    assert result["success"] is True
    assert result["arxiv_id"] == "2308.15022"
    assert result["title"] == "Recursive Memory"
    assert result["authors"] == ["Qingyue Wang", "Liang Ding"]
    assert result["section_count"] == 2
    assert result["sections"] == [
        {"name": "Abstract", "level": 0, "token_count": 30},
        {"name": "1 Introduction", "level": 1, "token_count": 120},
    ]
    assert result["pdf_url"] == "https://arxiv.org/pdf/2308.15022"


def test_cmd_read_section_returns_content_and_char_count(monkeypatch):
    module = load_module()

    class FakeReader:
        def __init__(self, **kwargs):
            pass

        def section(self, arxiv_id, section_name):
            assert arxiv_id == "2308.15022"
            assert section_name == "introduction"
            return "This is the introduction."

    monkeypatch.setattr(module, "Reader", FakeReader)
    result = module.cmd_read_section("2308.15022", "introduction", token="test-token")

    assert result == {
        "success": True,
        "arxiv_id": "2308.15022",
        "abs_url": "https://arxiv.org/abs/2308.15022",
        "section": "introduction",
        "content": "This is the introduction.",
        "char_count": 25,
        "error": None,
    }
