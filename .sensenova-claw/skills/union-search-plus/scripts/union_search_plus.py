#!/usr/bin/env python3
"""union-search-plus 统一入口。

调用 vendor 的 union-search CLI，并返回适配后的统一结构，便于与 serper 主链合并。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# 确保同目录模块可导入
sys.path.insert(0, str(Path(__file__).resolve().parent))

from search_fusion import deduplicate_and_rank


def _extract_json_from_text(text: str) -> Any:
    if not text:
        raise ValueError("empty output")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch not in "[{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[idx:])
            return obj
        except json.JSONDecodeError:
            continue

    raise ValueError("no valid json found")


def _vendor_root() -> Path:
    return Path(__file__).resolve().parents[1] / "vendor" / "union-search-skill"


def _resolve_env_file(env_file: str, vendor_root: Path) -> str:
    candidate = Path(env_file).expanduser()
    if candidate.is_absolute():
        return str(candidate)

    cwd_candidate = (Path.cwd() / candidate).resolve()
    if cwd_candidate.exists():
        return str(cwd_candidate)

    vendor_candidate = (vendor_root / candidate).resolve()
    if vendor_candidate.exists():
        return str(vendor_candidate)

    return str(cwd_candidate)


def _flatten_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    # 兼容 CLI envelope
    payload = data.get("data", data)

    if isinstance(payload, dict) and isinstance(payload.get("final_items"), list):
        return [x for x in payload["final_items"] if isinstance(x, dict)]

    if isinstance(payload, dict) and isinstance(payload.get("results"), dict):
        out: list[dict[str, Any]] = []
        for platform, result in payload["results"].items():
            if not isinstance(result, dict):
                continue
            items = result.get("items")
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                normalized = dict(item)
                normalized.setdefault("_source_platform", platform)
                out.append(normalized)
        return out

    return []


def _build_command(
    vendor_root: Path,
    query: str,
    limit: int,
    timeout: int,
    env_file: str,
    group: str | None = None,
    platforms: list[str] | None = None,
) -> list[str]:
    entry = vendor_root / "union_search_cli.py"
    cmd = [
        sys.executable,
        str(entry),
        "search",
        query,
        "--limit",
        str(limit),
        "--timeout",
        str(timeout),
        "--deduplicate",
        "--env-file",
        env_file,
        "--format",
        "json",
        "--pretty",
    ]
    if platforms:
        cmd.extend(["--platforms", *platforms])
    elif group:
        cmd.extend(["--group", group])
    else:
        cmd.extend(["--group", "preferred"])
    return cmd


def run_union_search(
    query: str,
    limit: int,
    timeout: int,
    env_file: str,
    group: str | None = None,
    platforms: list[str] | None = None,
) -> dict[str, Any]:
    vendor_root = _vendor_root()
    source_label = ", ".join(platforms) if platforms else (group or "preferred")
    if not vendor_root.exists():
        return {
            "success": False,
            "provider": "union-search-plus",
            "query": query,
            "source": source_label,
            "items": [],
            "error": f"vendor path not found: {vendor_root}",
        }

    resolved_env_file = _resolve_env_file(env_file, vendor_root)
    cmd = _build_command(
        vendor_root,
        query,
        limit,
        timeout,
        resolved_env_file,
        group=group,
        platforms=platforms,
    )
    try:
        proc = subprocess.run(
            cmd,
            cwd=vendor_root,
            capture_output=True,
            text=True,
            timeout=max(timeout + 10, 30),
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "success": False,
            "provider": "union-search-plus",
            "query": query,
            "source": source_label,
            "items": [],
            "error": f"vendor command timeout after {exc.timeout} seconds",
            "command": cmd,
        }
    except OSError as exc:
        return {
            "success": False,
            "provider": "union-search-plus",
            "query": query,
            "source": source_label,
            "items": [],
            "error": str(exc).strip() or type(exc).__name__,
            "command": cmd,
        }

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        return {
            "success": False,
            "provider": "union-search-plus",
            "query": query,
            "source": source_label,
            "items": [],
            "error": detail,
            "command": cmd,
        }

    raw = _extract_json_from_text(proc.stdout)
    if not isinstance(raw, dict):
        return {
            "success": False,
            "provider": "union-search-plus",
            "query": query,
            "source": source_label,
            "items": [],
            "error": "unexpected output type",
            "command": cmd,
        }

    items = _flatten_items(raw)
    merged = deduplicate_and_rank(items, query=query)

    payload = raw.get("data", {}) if isinstance(raw.get("data", {}), dict) else {}
    summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
    successful_platforms = int(summary.get("successful", 0) or 0)
    failed_platforms = int(summary.get("failed", 0) or 0)
    raw_success = bool(raw.get("success", False))
    effective_success = raw_success or successful_platforms > 0

    return {
        "success": effective_success,
        "provider": "union-search-plus",
        "query": query,
        "source": source_label,
        "items": merged,
        "summary": {
            "total_items": len(merged),
            "raw_items": len(items),
            "deduplicated_removed": len(items) - len(merged),
            "successful_platforms": successful_platforms,
            "failed_platforms": failed_platforms,
            "partial_failure": failed_platforms > 0,
        },
        "raw": raw,
        "command": cmd,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="union-search-plus 统一入口")
    parser.add_argument("query", help="搜索关键词")
    parser.add_argument(
        "--group",
        default=None,
        choices=["preferred", "all", "dev", "social", "search", "no_api_key", "tools"],
        help="搜索分组（与 --platforms 二选一）",
    )
    parser.add_argument(
        "--platforms",
        nargs="+",
        default=None,
        help="指定平台列表，如 --platforms zhihu bilibili github（与 --group 二选一）",
    )
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args()

    result = run_union_search(
        query=args.query,
        group=args.group,
        platforms=args.platforms,
        limit=max(1, args.limit),
        timeout=max(10, args.timeout),
        env_file=args.env_file,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
