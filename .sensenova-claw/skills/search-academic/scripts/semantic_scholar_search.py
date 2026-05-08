#!/usr/bin/env python3
"""Semantic Scholar 论文搜索。通过 Semantic Scholar Graph API。"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "_search-common"))

from search_utils import build_parser, get_client, make_item, make_result, print_json

API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
MAX_429_ATTEMPTS = 4
BASE_429_DELAY_SECONDS = 1.0

FIELDS = ",".join([
    "title", "abstract", "tldr", "year", "venue", "publicationVenue", "publicationDate",
    "authors", "citationCount", "influentialCitationCount",
    "referenceCount", "isOpenAccess", "openAccessPdf",
    "externalIds", "fieldsOfStudy", "publicationTypes", "journal",
])


def _retry_after_delay(response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            pass
    return BASE_429_DELAY_SECONDS * (2 ** attempt)


def _get_with_429_retry(client, url: str, *, params: dict) -> object:
    for attempt in range(MAX_429_ATTEMPTS):
        resp = client.get(url, params=params)
        if getattr(resp, "status_code", None) != 429:
            resp.raise_for_status()
            return resp
        if attempt == MAX_429_ATTEMPTS - 1:
            resp.raise_for_status()
            return resp
        time.sleep(_retry_after_delay(resp, attempt))
    raise RuntimeError("unreachable")


def search(query: str, limit: int, api_key: str | None = None) -> list[dict]:
    """执行 Semantic Scholar 搜索。"""
    headers: dict[str, str] = {}
    if api_key:
        headers["x-api-key"] = api_key

    params = {
        "query": query,
        "limit": min(limit, 100),
        "fields": FIELDS,
    }

    with get_client(timeout=30, headers=headers) as client:
        resp = _get_with_429_retry(client, API_URL, params=params)
        data = resp.json()

    items = []
    for paper in data.get("data", [])[:limit]:
        authors = [a.get("name", "") for a in paper.get("authors", [])]

        open_access_pdf = None
        if paper.get("openAccessPdf"):
            open_access_pdf = paper["openAccessPdf"].get("url")

        external_ids = paper.get("externalIds") or {}
        doi = external_ids.get("DOI")
        arxiv_id = external_ids.get("ArXiv")

        paper_id = paper.get("paperId", "")
        url = f"https://www.semanticscholar.org/paper/{paper_id}"

        # 摘要：优先用 abstract，缺失时降级用 tldr
        abstract = paper.get("abstract") or ""
        tldr = (paper.get("tldr") or {}).get("text")
        snippet = abstract or tldr or ""

        # 期刊/会议：venue（脏字符串）+ publicationVenue（结构化）
        venue = paper.get("venue") or (paper.get("journal") or {}).get("name")
        pub_venue = paper.get("publicationVenue") or {}
        publication_venue = {
            k: pub_venue[k]
            for k in ("id", "name", "type", "url")
            if pub_venue.get(k)
        } or None

        items.append(make_item(
            title=paper.get("title") or "",
            url=url,
            snippet=snippet,
            tldr=tldr,
            authors=authors,
            year=paper.get("year"),
            venue=venue if venue else None,
            publication_venue=publication_venue,
            publication_date=paper.get("publicationDate"),
            citation_count=paper.get("citationCount"),
            influential_citation_count=paper.get("influentialCitationCount"),
            reference_count=paper.get("referenceCount"),
            is_open_access=paper.get("isOpenAccess"),
            open_access_pdf=open_access_pdf,
            fields_of_study=paper.get("fieldsOfStudy") or None,
            publication_types=paper.get("publicationTypes") or None,
            doi=doi,
            arxiv_id=arxiv_id,
            paper_id=paper_id,
        ))

    return items


def main():
    parser = build_parser("搜索 Semantic Scholar 学术论文")
    parser.add_argument("--api-key", help="Semantic Scholar API Key（可选，提高限额）")
    args = parser.parse_args()

    try:
        items = search(args.query, args.limit, getattr(args, "api_key", None))
        print_json(make_result(True, args.query, "semantic_scholar", items))
    except Exception as e:
        print_json(make_result(False, args.query, "semantic_scholar", [], str(e)))
        sys.exit(1)


if __name__ == "__main__":
    main()
