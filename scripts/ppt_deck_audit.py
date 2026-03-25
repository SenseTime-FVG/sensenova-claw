from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

Json = dict[str, Any]

_STRUCTURE_BLOCK_TAGS = ("p", "ul", "ol", "table", "blockquote", "pre", "figure")
_CLAIM_HINTS = ("因为", "因此", "所以", "表明", "说明", "显示", "证明", "结论", "建议", "必须")
_EVIDENCE_HINTS = (
    r"\d+",
    r"https?://",
    r"\b\w+@\w+\.\w+\b",
    r"图\s*\d+",
    r"表\s*\d+",
    r"（\d+）",
    r"\[\d+\]",
)


def _strip_html_tags(text: str) -> str:
    """去掉 HTML 标签，保留可用于粗略统计的纯文本。"""
    return re.sub(r"<[^>]+>", " ", text)


def _count_structure_blocks(html_text: str) -> int:
    """统计正文页里可感知的结构块数量。"""
    count = 0
    for tag in _STRUCTURE_BLOCK_TAGS:
        count += len(re.findall(fr"<{tag}\b", html_text, flags=re.IGNORECASE))
    return count


def _classify_claim_density(html_text: str) -> str:
    """按论点表达强度给出粗略密度分级。"""
    text = html.unescape(_strip_html_tags(html_text))
    text = re.sub(r"\s+", " ", text).strip()
    structure_blocks = _count_structure_blocks(html_text)
    sentence_count = len(re.findall(r"[。！？!?]+", text))
    claim_hints = sum(text.count(hint) for hint in _CLAIM_HINTS)
    if structure_blocks <= 1 and sentence_count <= 2 and claim_hints == 0:
        return "low"
    if structure_blocks <= 3 and sentence_count <= 5:
        return "medium"
    return "high"


def _classify_evidence_density(html_text: str) -> str:
    """按证据、数据、链接等可见线索给出粗略密度分级。"""
    text = html.unescape(_strip_html_tags(html_text))
    text = re.sub(r"\s+", " ", text).strip()
    evidence_hits = 0
    for pattern in _EVIDENCE_HINTS:
        evidence_hits += len(re.findall(pattern, text, flags=re.IGNORECASE))
    if evidence_hits == 0:
        return "low"
    if evidence_hits <= 3:
        return "medium"
    return "high"


def audit_deck(deck_dir: Path) -> Json:
    """扫描 deck 目录下的页面文件，输出轻量审计报告。"""
    pages: list[Json] = []
    for html_path in sorted((deck_dir / "pages").glob("page_*.html")):
        html_text = html_path.read_text(encoding="utf-8")
        pages.append(
            {
                "page": html_path.name,
                "claim_density": _classify_claim_density(html_text),
                "evidence_density": _classify_evidence_density(html_text),
                "structure_block_count": _count_structure_blocks(html_text),
            }
        )
    return {"pages": pages}


def main() -> None:
    """命令行入口，方便本地快速检查 deck 审计结果。"""
    import argparse

    parser = argparse.ArgumentParser(description="Audit PPT deck content density.")
    parser.add_argument("deck_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit_deck(args.deck_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
