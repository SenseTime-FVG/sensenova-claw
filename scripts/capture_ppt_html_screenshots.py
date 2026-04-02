"""批量截取 PPT HTML 结果页。

推荐用法：
  conda activate pipeline
  python scripts/capture_ppt_html_screenshots.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agentos.utils.ppt_html_screenshot import (
    DEFAULT_CAPTURE_ROOT,
    DEFAULT_VIEWPORT_HEIGHT,
    DEFAULT_VIEWPORT_WIDTH,
    capture_with_playwright,
    discover_capture_tasks,
    summarize_capture_results,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="批量为 PPT HTML 页面截图")
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_CAPTURE_ROOT,
        help="PPT 结果根目录，默认扫描 ~/.agentos/workdir/default",
    )
    parser.add_argument(
        "--pattern",
        default="*",
        help="结果目录匹配模式，例如 'Gold_*' 或 '20260319*'",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="覆盖已有截图",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=DEFAULT_VIEWPORT_WIDTH,
        help="浏览器视口宽度，默认 1280",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=DEFAULT_VIEWPORT_HEIGHT,
        help="浏览器视口高度，默认 720",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    tasks = discover_capture_tasks(args.root, pattern=args.pattern)

    if not tasks:
        print(f"[INFO] 未在 {args.root} 中发现可截图的 HTML 页面。")
        return 0

    print(f"[INFO] 共发现 {len(tasks)} 个 HTML 页面，开始截图。")
    results = capture_with_playwright(
        tasks,
        overwrite=args.overwrite,
        width=args.width,
        height=args.height,
    )
    summary = summarize_capture_results(results)

    for result in results:
        if result.status == "failed":
            print(
                f"[FAILED] {result.task.html_path} -> {result.task.screenshot_path} | {result.error}"
            )
        elif result.status == "skipped":
            print(f"[SKIPPED] {result.task.screenshot_path}")
        else:
            print(f"[CAPTURED] {result.task.screenshot_path}")

    print(
        "[SUMMARY] "
        f"captured={summary['captured']} skipped={summary['skipped']} failed={summary['failed']}"
    )
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
