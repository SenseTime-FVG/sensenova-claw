#!/usr/bin/env python3
"""ArXiv 论文搜索。通过 ArXiv API（返回 Atom XML）。"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "_search-common"))

from search_utils import build_parser, get_client, make_item, make_result, print_json

API_URL = "https://export.arxiv.org/api/query"

# Atom XML 命名空间
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


def search(query: str, limit: int, category: str | None = None, sort_by: str = "relevance") -> list[dict]:
    """执行 ArXiv 搜索。"""
    # 构建查询字符串
    search_query = f"all:{query}"
    if category:
        search_query = f"cat:{category} AND all:{query}"

    sort_map = {
        "relevance": "relevance",
        "date": "lastUpdatedDate",
        "submitted": "submittedDate",
    }

    params = {
        "search_query": search_query,
        "start": 0,
        "max_results": min(limit, 100),
        "sortBy": sort_map.get(sort_by, "relevance"),
        "sortOrder": "descending",
    }

    with get_client(timeout=30, headers={"Accept": "application/xml"}) as client:
        resp = client.get(API_URL, params=params)
        resp.raise_for_status()

    root = ET.fromstring(resp.text)
    items = []

    for entry in root.findall("atom:entry", NS)[:limit]:
        title = _text(entry, "atom:title").replace("\n", " ").strip()
        summary = _text(entry, "atom:summary").replace("\n", " ").strip()
        published = _text(entry, "atom:published")
        updated = _text(entry, "atom:updated")

        # 获取论文链接（优先 abs 页面）
        url = ""
        pdf_url = ""
        for link in entry.findall("atom:link", NS):
            href = link.get("href", "")
            if link.get("title") == "pdf":
                pdf_url = href
            elif link.get("type") == "text/html" or "/abs/" in href:
                url = href
        if not url:
            url = _text(entry, "atom:id")

        # 获取作者
        authors = [_text(a, "atom:name") for a in entry.findall("atom:author", NS)]

        # 获取分类
        categories = [c.get("term", "") for c in entry.findall("atom:category", NS)]

        comment = _text(entry, "arxiv:comment")
        journal_ref = _text(entry, "arxiv:journal_ref")
        doi = _text(entry, "arxiv:doi")
        primary_category = entry.find("arxiv:primary_category", NS)
        primary_cat = primary_category.get("term", "") if primary_category is not None else ""

        items.append(make_item(
            title=title,
            url=url,
            snippet=summary,
            authors=authors,
            published=published,
            updated=updated,
            pdf_url=pdf_url,
            categories=categories,
            primary_category=primary_cat if primary_cat else None,
            comment=comment if comment else None,
            journal_ref=journal_ref if journal_ref else None,
            doi=doi if doi else None,
        ))

    return items


def _text(elem: ET.Element, tag: str) -> str:
    """安全获取子元素文本。"""
    child = elem.find(tag, NS)
    return child.text.strip() if child is not None and child.text else ""


def main():
    parser = build_parser("搜索 ArXiv 学术论文")
    parser.add_argument("--category", "-c", help="ArXiv 分类（如 cs.AI, cs.CL, math.CO）")
    parser.add_argument("--sort", default="relevance",
                        choices=["relevance", "date", "submitted"],
                        help="排序方式（默认 relevance）")
    args = parser.parse_args()

    try:
        items = search(args.query, args.limit, args.category, args.sort)
        print_json(make_result(True, args.query, "arxiv", items))
    except Exception as e:
        print_json(make_result(False, args.query, "arxiv", [], str(e)))
        sys.exit(1)


if __name__ == "__main__":
    main()
