#!/usr/bin/env python3
"""小红书搜索。通过 xhs PyPI 库（内置签名生成，稳定性较高）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "_search-common"))

from search_utils import build_parser, get_key, make_item, make_result, print_json


def _make_sign_fn():
    """构造签名函数，适配 XhsClient 的 external_sign 接口。"""
    from xhs.core import sign as _builtin_sign

    def sign_fn(url, data=None, a1="", web_session=""):
        return _builtin_sign(url, data, a1=a1)

    return sign_fn


def search(query: str, limit: int, cookie: str | None = None, sort: str = "general") -> list[dict]:
    """执行小红书搜索。"""
    if not cookie:
        raise ValueError("需要 XHS_COOKIE 环境变量。请从浏览器开发者工具获取小红书 cookie。")

    from xhs import XhsClient
    from xhs.core import SearchSortType

    sort_map = {
        "general": SearchSortType.GENERAL,
        "hot": SearchSortType.MOST_POPULAR,
        "new": SearchSortType.LATEST,
    }

    client = XhsClient(cookie=cookie, sign=_make_sign_fn())
    data = client.get_note_by_keyword(
        keyword=query,
        page=1,
        page_size=min(limit, 20),
        sort=sort_map.get(sort, SearchSortType.GENERAL),
    )

    items = []
    for note in data.get("items", [])[:limit]:
        note_card = note.get("note_card", note)
        note_id = note.get("id") or note_card.get("note_id", "")
        user = note_card.get("user", {})

        title = note_card.get("display_title") or note_card.get("title") or ""
        desc = note_card.get("desc", "")

        interact = note_card.get("interact_info", {})

        items.append(make_item(
            title=title,
            url=f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else "",
            snippet=desc[:300],
            author=user.get("nickname", ""),
            liked_count=interact.get("liked_count"),
            collected_count=interact.get("collected_count"),
            type=note_card.get("type", ""),
        ))

    return items


def main():
    parser = build_parser("搜索小红书笔记")
    parser.add_argument("--cookie", help="小红书 Cookie（也可通过 XHS_COOKIE 环境变量设置，必填）")
    parser.add_argument("--sort", default="general",
                        choices=["general", "hot", "new"],
                        help="排序方式：general=综合, hot=热度, new=最新（默认 general）")
    args = parser.parse_args()

    cookie = get_key("XHS_COOKIE", args.cookie)
    try:
        items = search(args.query, args.limit, cookie, args.sort)
        print_json(make_result(True, args.query, "xiaohongshu", items))
    except Exception as e:
        print_json(make_result(False, args.query, "xiaohongshu", [], str(e)))
        sys.exit(1)


if __name__ == "__main__":
    main()
