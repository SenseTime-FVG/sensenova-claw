import importlib.util
import json
import sys
import types
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / ".sensenova-claw"
    / "skills"
    / "search-academic"
    / "scripts"
    / "paper.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("paper", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_read_arxiv_full_text_falls_back_and_normalizes_output(monkeypatch):
    module = load_module()
    calls = []

    def fake_call_provider(provider, paper_id, section):
        calls.append((provider.provider, paper_id, section))
        if provider.provider == "arxiv_html":
            return {"success": False, "arxiv_id": paper_id, "content": None, "error": "HTML unavailable"}
        return {
            "success": True,
            "arxiv_id": paper_id,
            "abs_url": f"https://arxiv.org/abs/{paper_id}",
            "content": "DeepXiv full text",
            "char_count": 17,
            "token_count": 123,
            "error": None,
        }

    monkeypatch.setattr(module, "_call_provider", fake_call_provider)

    result = module.read_paper("arXiv:2603.00729", source="arxiv")

    assert calls == [
        ("arxiv_html", "2603.00729", None),
        ("deepxiv", "2603.00729", None),
    ]
    assert result["success"] is True
    assert result["arxiv_id"] == "2603.00729"
    assert result["source"] == "arxiv"
    assert result["provider"] == "deepxiv"
    assert result["provider_rating"] is None
    assert result["content"] == "DeepXiv full text"
    assert result["token_count"] == 123
    assert result["attempts"] == [
        {"provider": "arxiv_html", "success": False, "error": "HTML unavailable"},
        {"provider": "deepxiv", "success": True, "error": None},
    ]


def test_read_arxiv_section_skips_pdf_provider(monkeypatch):
    module = load_module()
    calls = []

    def fake_call_provider(provider, paper_id, section):
        calls.append(provider.provider)
        assert provider.provider != "arxiv_pdf"
        return {"success": False, "arxiv_id": paper_id, "content": None, "error": f"{provider.provider} failed"}

    monkeypatch.setattr(module, "_call_provider", fake_call_provider)

    result = module.read_paper("2603.00729", section="method")

    assert calls == ["arxiv_html", "deepxiv"]
    assert result["success"] is False
    assert result["arxiv_id"] == "2603.00729"
    assert result["source"] == "arxiv"
    assert result["provider"] is None
    assert result["provider_rating"] is None
    assert result["section"] == "method"
    assert "arxiv_html failed" in result["error"]
    assert "deepxiv failed" in result["error"]


def test_read_pmc_full_text_builds_content_from_pmc_sections(monkeypatch):
    module = load_module()
    fake_root = types.SimpleNamespace()

    fake_pmc_module = types.SimpleNamespace(
        fetch_pmc_xml=lambda pmc_num, api_key=None: fake_root,
        extract_all_sections=lambda root: [
            {"name": "Abstract", "level": 0, "text": "Abstract text.", "subsections": []},
            {
                "name": "Methods",
                "level": 1,
                "text": "Methods text.",
                "subsections": [
                    {"name": "Data", "level": 2, "text": "Data text.", "subsections": []},
                ],
            },
        ],
    )
    fake_root.findtext = lambda path, default="": {
        ".//article-title": "PMC Sample",
        ".//article-id[@pub-id-type='pmid']": "12345678",
    }.get(path, default)

    monkeypatch.setitem(sys.modules, "pmc_paper", fake_pmc_module)

    result = module.read_paper("PMC11119143", source="pmc")

    assert result["success"] is True
    assert result["pmc_id"] == "PMC11119143"
    assert result["source"] == "pmc"
    assert result["provider"] == "pmc"
    assert result["provider_rating"] is None
    assert result["title"] == "PMC Sample"
    assert result["pmid"] == "12345678"
    assert result["content"] == (
        "Abstract\n"
        "Abstract text.\n\n"
        "Methods\n"
        "Methods text.\n\n"
        "Data\n"
        "Data text."
    )
    assert result["section_count"] == 3


def test_call_provider_uses_provider_specific_functions_without_extra_args(monkeypatch):
    module = load_module()
    calls = []

    fake_arxiv = types.SimpleNamespace(
        cmd_read_full_text=lambda arxiv_id: calls.append(("full", arxiv_id)) or {
            "success": True,
            "arxiv_id": arxiv_id,
            "content": "HTML full text",
            "error": None,
        },
        cmd_read_section=lambda arxiv_id, section: calls.append(("section", arxiv_id, section)) or {
            "success": True,
            "arxiv_id": arxiv_id,
            "section": "1 Introduction",
            "content": "Intro text",
            "error": None,
        },
    )
    fake_pdf = types.SimpleNamespace(
        cmd_read_pdf=lambda arxiv_id: calls.append(("pdf", arxiv_id)) or {
            "success": True,
            "arxiv_id": arxiv_id,
            "content": "PDF full text",
            "error": None,
        },
    )

    monkeypatch.setitem(sys.modules, "arxiv_paper", fake_arxiv)
    monkeypatch.setitem(sys.modules, "arxiv_pdf_paper", fake_pdf)

    arxiv_html = module.PROVIDER_GROUPS["arxiv"][0]
    arxiv_pdf = module.PROVIDER_GROUPS["arxiv"][2]

    assert module._call_provider(arxiv_html, "2603.00729", None)["content"] == "HTML full text"
    assert module._call_provider(arxiv_html, "2603.00729", "intro")["content"] == "Intro text"
    assert module._call_provider(arxiv_pdf, "2603.00729", None)["content"] == "PDF full text"
    assert calls == [
        ("full", "2603.00729"),
        ("section", "2603.00729", "intro"),
        ("pdf", "2603.00729"),
    ]


def test_main_outputs_unified_json(monkeypatch, capsys):
    module = load_module()

    def fake_read_paper(paper_id, source="arxiv", section=None):
        return {
            "success": True,
            "arxiv_id": paper_id,
            "source": source,
            "provider": "arxiv_html",
            "provider_rating": None,
            "section": section,
            "content": "Intro text",
            "error": None,
        }

    monkeypatch.setattr(module, "read_paper", fake_read_paper)
    monkeypatch.setattr(sys, "argv", ["paper.py", "2603.00729", "--section", "intro"])

    module.main()

    output = json.loads(capsys.readouterr().out)
    assert output == {
        "success": True,
        "arxiv_id": "2603.00729",
        "source": "arxiv",
        "provider": "arxiv_html",
        "provider_rating": None,
        "section": "intro",
        "content": "Intro text",
        "error": None,
    }


def test_main_writes_json_output_file(monkeypatch, capsys, tmp_path):
    module = load_module()
    output_path = tmp_path / "nested" / "paper.json"

    def fake_read_paper(paper_id, source="arxiv", section=None):
        return {
            "success": True,
            "arxiv_id": paper_id,
            "source": source,
            "provider": "arxiv_html",
            "provider_rating": None,
            "content": "Full text",
            "error": None,
        }

    monkeypatch.setattr(module, "read_paper", fake_read_paper)
    monkeypatch.setattr(sys, "argv", ["paper.py", "2603.00729", "--output", str(output_path)])

    module.main()

    stdout_json = json.loads(capsys.readouterr().out)
    file_json = json.loads(output_path.read_text(encoding="utf-8"))
    expected = {
        "success": True,
        "arxiv_id": "2603.00729",
        "source": "arxiv",
        "provider": "arxiv_html",
        "provider_rating": None,
        "content": "Full text",
        "error": None,
        "output_path": str(output_path.resolve()),
    }
    assert stdout_json == expected
    assert file_json == expected
