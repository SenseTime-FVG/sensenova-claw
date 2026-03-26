#!/usr/bin/env python3
"""合并主链与 union-search 补充结果。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# 确保同目录模块可导入
sys.path.insert(0, str(Path(__file__).resolve().parent))

from search_fusion import deduplicate_and_rank


def _collect_items(data: dict[str, Any], default_provider: str) -> list[dict[str, Any]]:
    """从不同结构提取 item 列表。"""
    if isinstance(data.get("items"), list):
        out: list[dict[str, Any]] = []
        for item in data["items"]:
            if isinstance(item, dict):
                normalized = dict(item)
                normalized.setdefault("provider", default_provider)
                out.append(normalized)
        return out

    results = data.get("results")
    if isinstance(results, dict):
        out: list[dict[str, Any]] = []
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
                    normalized.setdefault("provider", default_provider)
                    out.append(normalized)
        return out

    return []


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        print(f"警告: 文件不存在 {path}，使用空结果", file=sys.stderr)
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="合并搜索结果并去重重排")
    parser.add_argument("--primary", required=True, help="主链 JSON")
    parser.add_argument("--supplement", required=True, help="补充链 JSON")
    parser.add_argument("--query", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    primary = _load(Path(args.primary))
    supplement = _load(Path(args.supplement))

    primary_items = _collect_items(primary, default_provider="primary")
    supplement_items = _collect_items(supplement, default_provider="union-search-plus")

    merged = deduplicate_and_rank(primary_items + supplement_items, query=args.query)

    payload = {
        "query": args.query,
        "summary": {
            "primary_items": len(primary_items),
            "supplement_items": len(supplement_items),
            "merged_items": len(merged),
            "deduplicated_removed": len(primary_items) + len(supplement_items) - len(merged),
        },
        "items": merged,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
