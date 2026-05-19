#!/usr/bin/env python3
"""Search global news articles through the free, keyless GDELT DOC 2.0 API."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "_search-common"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from search_utils import get_client, make_item, make_result, print_json
from _filters import CryptoQueryError, filter_crypto_items, reject_crypto_query


API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


def search(
    query: str,
    limit: int,
    timespan: str = "1week",
    sort: str = "hybridrel",
    source_country: str | None = None,
    source_lang: str | None = None,
) -> list[dict]:
    reject_crypto_query(query)
    params: dict[str, str | int] = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": min(max(limit * 3, limit), 250),
        "timespan": timespan,
        "sort": sort,
    }
    if source_country:
        params["sourcecountry"] = source_country
    if source_lang:
        params["sourcelang"] = source_lang

    with get_client(timeout=30) as client:
        resp = client.get(API_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    items = []
    for article in data.get("articles", []):
        title = article.get("title") or ""
        url = article.get("url") or ""
        domain = article.get("domain") or ""
        snippet_parts = [
            article.get("language") or "",
            article.get("sourcecountry") or "",
            domain,
        ]
        items.append(make_item(
            title=title,
            url=url,
            snippet=" | ".join(part for part in snippet_parts if part),
            seen_date=article.get("seendate"),
            domain=domain,
            language=article.get("language"),
            source_country=article.get("sourcecountry"),
            social_image=article.get("socialimage"),
        ))
        if len(filter_crypto_items(items)) >= limit:
            break
    return filter_crypto_items(items)[:limit]


def main() -> None:
    parser = argparse.ArgumentParser(description="搜索 GDELT 全球新闻文章（免费、免 API key）")
    parser.add_argument("query", help="新闻关键词；加密货币/区块链/Web3 相关查询会被拒绝")
    parser.add_argument("--limit", "-n", type=int, default=10, help="返回结果数量（默认 10）")
    parser.add_argument("--timespan", default="1week", help="时间范围，如 1h、24h、1week、3months（默认 1week）")
    parser.add_argument("--sort", default="hybridrel", choices=["hybridrel", "datedesc"], help="排序方式（默认 hybridrel）")
    parser.add_argument("--source-country", help="按来源国家过滤，如 United States、China")
    parser.add_argument("--source-lang", help="按来源语言过滤，如 English、Chinese")
    args = parser.parse_args()

    try:
        items = search(args.query, args.limit, args.timespan, args.sort, args.source_country, args.source_lang)
        print_json(make_result(True, args.query, "gdelt", items))
    except CryptoQueryError as exc:
        print_json(make_result(False, args.query, "gdelt", [], str(exc)))
        sys.exit(2)
    except Exception as exc:
        print_json(make_result(False, args.query, "gdelt", [], str(exc)))
        sys.exit(1)


if __name__ == "__main__":
    main()
