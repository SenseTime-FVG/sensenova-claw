import tempfile
from pathlib import Path
import unittest

from scripts.ppt_deck_audit import audit_deck


class TestPptDeckAudit(unittest.TestCase):
    def test_audit_detects_sparse_content_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            deck_dir = Path(tmp_dir) / "deck"
            pages_dir = deck_dir / "pages"
            pages_dir.mkdir(parents=True)
            (pages_dir / "page_01.html").write_text(
                "<div id='ct'><h1>标题</h1><ul><li>一条 bullet</li></ul></div>",
                encoding="utf-8",
            )

            report = audit_deck(deck_dir)

            self.assertEqual(report["pages"][0]["claim_density"], "low")
            self.assertEqual(report["pages"][0]["evidence_density"], "low")
            self.assertEqual(report["pages"][0]["structure_block_count"], 1)

    def test_audit_counts_multiple_div_cards_as_structure_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            deck_dir = Path(tmp_dir) / "deck"
            pages_dir = deck_dir / "pages"
            pages_dir.mkdir(parents=True)
            (pages_dir / "page_01.html").write_text(
                "<div id='ct'><div class='card'>A</div><div class='card'>B</div></div>",
                encoding="utf-8",
            )

            report = audit_deck(deck_dir)

            self.assertGreater(report["pages"][0]["structure_block_count"], 0)

    def test_audit_does_not_treat_plain_year_title_as_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            deck_dir = Path(tmp_dir) / "deck"
            pages_dir = deck_dir / "pages"
            pages_dir.mkdir(parents=True)
            (pages_dir / "page_01.html").write_text(
                "<div id='ct'><h1>2026 产品路线图</h1><p>概览</p></div>",
                encoding="utf-8",
            )

            report = audit_deck(deck_dir)

            self.assertEqual(report["pages"][0]["evidence_density"], "low")

    def test_audit_returns_stable_multi_page_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            deck_dir = Path(tmp_dir) / "deck"
            pages_dir = deck_dir / "pages"
            pages_dir.mkdir(parents=True)
            (pages_dir / "page_01.html").write_text(
                "<div id='ct'><h1>标题</h1><ul><li>一条 bullet</li></ul></div>",
                encoding="utf-8",
            )
            (pages_dir / "page_02.html").write_text(
                "<div id='ct'><p>更多内容</p><p>第二段</p></div>",
                encoding="utf-8",
            )

            report = audit_deck(deck_dir)

            self.assertEqual(len(report["pages"]), 2)
            self.assertEqual([page["page"] for page in report["pages"]], ["page_01.html", "page_02.html"])
            self.assertIn("claim_density", report["pages"][0])
            self.assertIn("evidence_density", report["pages"][0])
            self.assertIn("structure_block_count", report["pages"][0])


if __name__ == "__main__":
    unittest.main()
