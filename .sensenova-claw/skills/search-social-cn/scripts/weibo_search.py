#!/usr/bin/env python3
"""微博搜索。通过微博移动端 API（需要 cookie 认证）。"""

import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "_search-common"))

from search_utils import build_parser, get_client, get_key, make_item, make_result, print_json


SEARCH_URL = "https://m.weibo.cn/api/container/getIndex"


def search(query: str, limit: int, cookie: str | None = None, page: int = 1) -> list[dict]:
    """执行微博搜索。"""
    if not cookie:
        raise ValueError("需要 WEIBO_COOKIE 环境变量。请从浏览器开发者工具获取微博 cookie。")

    # containerid 格式: 100103type=1&q=关键词
    containerid = f"100103type=1&q={quote(query)}"

    headers = {
        "Cookie": cookie,
        "Referer": "https://m.weibo.cn/",
        "X-Requested-With": "XMLHttpRequest",
    }

    params = {
        "containerid": containerid,
        "page_type": "searchall",
        "page": page,
    }

    with get_client(headers=headers) as client:
        resp = client.get(SEARCH_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    if data.get("ok") != 1:
        msg = data.get("msg", "请求失败")
        raise RuntimeError(f"微博 API 错误: {msg}")

    items = []
    cards = data.get("data", {}).get("cards", [])
    for card in cards:
        # card_type 9 是普通微博
        if card.get("card_type") != 9:
            # card_group 中可能嵌套 card_type=9
            for sub in card.get("card_group", []):
                if sub.get("card_type") == 9:
                    item = _parse_mblog(sub.get("mblog", {}))
                    if item:
                        items.append(item)
            continue

        mblog = card.get("mblog", {})
        item = _parse_mblog(mblog)
        if item:
            items.append(item)

        if len(items) >= limit:
            break

    return items[:limit]


def _parse_mblog(mblog: dict) -> dict | None:
    if not mblog:
        return None

    mid = mblog.get("mid") or mblog.get("id", "")
    user = mblog.get("user", {}) or {}
    text = _strip_html(mblog.get("text", ""))

    if not text and not mblog.get("page_info"):
        return None

    screen_name = user.get("screen_name", "")
    url = f"https://m.weibo.cn/detail/{mid}" if mid else ""

    return make_item(
        title=f"@{screen_name}" if screen_name else "",
        url=url,
        snippet=text[:300],
        author=screen_name,
        reposts_count=mblog.get("reposts_count", 0),
        comments_count=mblog.get("comments_count", 0),
        attitudes_count=mblog.get("attitudes_count", 0),
        created_at=mblog.get("created_at"),
    )


def _strip_html(html: str) -> str:
    import re
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def main():
    parser = build_parser("搜索微博帖子")
    parser.add_argument("--cookie", help="微博 Cookie（也可通过 WEIBO_COOKIE 环境变量设置）")
    parser.add_argument("--page", type=int, default=1, help="页码（默认 1）")
    args = parser.parse_args()

    cookie = get_key("WEIBO_COOKIE", args.cookie)
    try:
        items = search(args.query, args.limit, cookie, args.page)
        print_json(make_result(True, args.query, "weibo", items))
    except Exception as e:
        print_json(make_result(False, args.query, "weibo", [], str(e)))
        sys.exit(1)


if __name__ == "__main__":
    main()
