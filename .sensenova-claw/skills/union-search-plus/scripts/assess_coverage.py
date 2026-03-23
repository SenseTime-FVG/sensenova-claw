#!/usr/bin/env python3
"""评估主链搜索结果覆盖度。

输入 serper/fetch 聚合结果，输出是否需要触发 union-search 补充。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from search_fusion import assess_insufficiency


def _collect_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    """兼容多种输入结构，提取 items 列表。"""
    if isinstance(data.get("items"), list):
        return [x for x in data["items"] if isinstance(x, dict)]

    # 支持 union 结构：results.{platform}.items
    results = data.get("results")
    if isinstance(results, dict):
        merged: list[dict[str, Any]] = []
        for platform, payload in results.items():
            if not isinstance(payload, dict):
                continue
            items = payload.get("items")
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    normalized = dict(item)
                    normalized.setdefault("_source_platform", str(platform))
                    merged.append(normalized)
        return merged

    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="评估搜索覆盖度并判断是否需补充来源")
    parser.add_argument("--input", required=True, help="输入 JSON 文件路径")
    parser.add_argument("--query", required=True, help="原始查询")
    parser.add_argument("--min-sources", type=int, default=3)
    parser.add_argument("--min-topic-coverage", type=float, default=0.45)
    parser.add_argument("--min-valid-evidence", type=int, default=6)
    args = parser.parse_args()

    input_path = Path(args.input)
    data = json.loads(input_path.read_text(encoding="utf-8"))
    items = _collect_items(data)

    result = assess_insufficiency(
        items=items,
        query=args.query,
        min_sources=args.min_sources,
        min_topic_coverage=args.min_topic_coverage,
        min_valid_evidence=args.min_valid_evidence,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
