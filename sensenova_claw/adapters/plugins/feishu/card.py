"""飞书消息卡片构建：将 Markdown 内容封装为 interactive card"""

import json


def build_markdown_card(text: str, title: str | None = None) -> str:
    """构建包含 Markdown 内容的最简飞书消息卡片"""
    elements = [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": text},
        }
    ]
    card: dict = {
        "config": {"wide_screen_mode": True},
        "elements": elements,
    }
    if title:
        card["header"] = {
            "title": {"tag": "plain_text", "content": title},
        }
    return json.dumps(card)
