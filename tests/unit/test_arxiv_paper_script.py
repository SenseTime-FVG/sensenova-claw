import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / ".sensenova-claw"
    / "skills"
    / "search-academic"
    / "scripts"
    / "arxiv_paper.py"
)


SAMPLE_HTML = """
<html>
  <body>
    <div class="ltx_abstract">
      <h6 class="ltx_title">Abstract</h6>
      <p>Abstract text.</p>
    </div>
    <section class="ltx_section">
      <h2 class="ltx_title">1 Introduction</h2>
      <p>Intro text.</p>
    </section>
    <section class="ltx_section">
      <h2 class="ltx_title">2 Method</h2>
      <p>Method text.</p>
    </section>
  </body>
</html>
"""


NESTED_HTML = """
<html>
  <body>
    <div class="ltx_abstract">
      <h6 class="ltx_title ltx_title_abstract">Abstract</h6>
      <p>Abstract text.</p>
    </div>
    <section id="S4" class="ltx_section">
      <h2 class="ltx_title ltx_title_section"><span class="ltx_tag">4 </span>Post-training</h2>
      <section id="S4.SS1" class="ltx_subsection">
        <h3 class="ltx_title ltx_title_subsection"><span class="ltx_tag">4.1 </span>Supervised Fine-tuning</h3>
        <p>SFT text.</p>
      </section>
    </section>
    <section id="bib" class="ltx_bibliography">
      <h2 class="ltx_title ltx_title_bibliography">References</h2>
      <ul>
        <li>Reference one.</li>
      </ul>
    </section>
    <section id="A1" class="ltx_appendix">
      <h2 class="ltx_title ltx_title_appendix"><span class="ltx_tag">Appendix A </span>Appendix</h2>
      <section id="A1.SS1" class="ltx_subsection">
        <h3 class="ltx_title ltx_title_subsection"><span class="ltx_tag">A.1 </span>Data Statistics</h3>
        <p>Appendix text.</p>
      </section>
    </section>
  </body>
</html>
"""


def load_module():
    spec = importlib.util.spec_from_file_location("arxiv_paper", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_cmd_read_full_text_returns_all_sections_in_order(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "fetch_html", lambda arxiv_id: SAMPLE_HTML)

    result = module.cmd_read_full_text("2409.05591")

    assert result == {
        "success": True,
        "arxiv_id": "2409.05591",
        "abs_url": "https://arxiv.org/abs/2409.05591",
        "html_url": "https://arxiv.org/html/2409.05591",
        "pdf_url": "https://arxiv.org/pdf/2409.05591",
        "content": (
            "Abstract\n"
            "Abstract text.\n\n"
            "1 Introduction\n"
            "Intro text.\n\n"
            "2 Method\n"
            "Method text."
        ),
        "char_count": 74,
        "section_count": 3,
        "sections": [
            {"name": "Abstract", "level": 0},
            {"name": "1 Introduction", "level": 1},
            {"name": "2 Method", "level": 1},
        ],
        "error": None,
    }


def test_main_without_section_outputs_full_text(monkeypatch, capsys):
    module = load_module()
    monkeypatch.setattr(module, "fetch_html", lambda arxiv_id: SAMPLE_HTML)
    monkeypatch.setattr(sys, "argv", ["arxiv_paper.py", "2409.05591"])

    module.main()

    output = json.loads(capsys.readouterr().out)
    assert output["success"] is True
    assert output["content"].startswith("Abstract\nAbstract text.")
    assert output["content"].endswith("2 Method\nMethod text.")
    assert output["section_count"] == 3


def test_extract_sections_keeps_child_only_parents_and_bibliography():
    module = load_module()

    sections = module.extract_sections(NESTED_HTML)

    assert [section["name"] for section in sections] == [
        "Abstract",
        "4 Post-training",
        "4.1 Supervised Fine-tuning",
        "References",
        "Appendix A Appendix",
        "A.1 Data Statistics",
    ]
    post_training = sections[1]
    assert post_training["text"] == ""
    assert "Supervised Fine-tuning" in post_training["full_text"]
    assert "SFT text." in post_training["full_text"]


def test_cmd_read_section_matches_references(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "fetch_html", lambda arxiv_id: NESTED_HTML)

    result = module.cmd_read_section("2603.00729v1", "references")

    assert result["success"] is True
    assert result["section"] == "References"
    assert result["content"] == "Reference one."


def test_cmd_read_full_text_includes_nested_section_content(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "fetch_html", lambda arxiv_id: NESTED_HTML)

    result = module.cmd_read_full_text("2603.00729v1")

    assert result["content"] == (
        "Abstract\n"
        "Abstract text.\n\n"
        "4 Post-training\n\n"
        "4.1 Supervised Fine-tuning\n"
        "SFT text.\n\n"
        "References\n"
        "Reference one.\n\n"
        "Appendix A Appendix\n\n"
        "A.1 Data Statistics\n"
        "Appendix text."
    )


def test_cmd_read_full_text_sections_only_include_abstract_and_top_level(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "fetch_html", lambda arxiv_id: NESTED_HTML)

    result = module.cmd_read_full_text("2603.00729v1")

    assert result["sections"] == [
        {"name": "Abstract", "level": 0},
        {"name": "4 Post-training", "level": 1},
        {"name": "References", "level": 1},
        {"name": "Appendix A Appendix", "level": 1},
    ]
