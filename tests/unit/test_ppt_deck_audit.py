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


if __name__ == "__main__":
    unittest.main()
