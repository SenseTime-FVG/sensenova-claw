from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

DEFAULT_CAPTURE_ROOT = Path("/home/wangbo4/.agentos/workdir/default")
DEFAULT_VIEWPORT_WIDTH = 1280
DEFAULT_VIEWPORT_HEIGHT = 720

CaptureStatus = Literal["captured", "skipped", "failed"]


@dataclass(frozen=True)
class CaptureTask:
    deck_dir: Path
    html_path: Path
    screenshot_path: Path


@dataclass(frozen=True)
class CaptureResult:
    task: CaptureTask
    status: CaptureStatus
    error: str | None = None


def discover_capture_tasks(root: Path, pattern: str = "*") -> list[CaptureTask]:
    tasks: list[CaptureTask] = []
    if not root.exists():
        return tasks

    for deck_dir in sorted(path for path in root.glob(pattern) if path.is_dir()):
        pages_dir = deck_dir / "pages"
        if not pages_dir.is_dir():
            continue

        for html_path in sorted(path for path in pages_dir.glob("*.html") if path.is_file()):
            tasks.append(
                CaptureTask(
                    deck_dir=deck_dir,
                    html_path=html_path,
                    screenshot_path=deck_dir / "screenshots" / f"{html_path.stem}.png",
                )
            )

    return tasks


def run_capture_tasks(
    tasks: list[CaptureTask],
    capture_page: Callable[[CaptureTask], None],
    overwrite: bool = False,
) -> list[CaptureResult]:
    results: list[CaptureResult] = []

    for task in tasks:
        if task.screenshot_path.exists() and not overwrite:
            results.append(CaptureResult(task=task, status="skipped"))
            continue

        task.screenshot_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            capture_page(task)
        except Exception as exc:  # pragma: no cover - 具体异常由调用方决定
            message = str(exc).strip() or type(exc).__name__
            results.append(CaptureResult(task=task, status="failed", error=message))
            continue

        results.append(CaptureResult(task=task, status="captured"))

    return results


def capture_with_playwright(
    tasks: list[CaptureTask],
    overwrite: bool = False,
    width: int = DEFAULT_VIEWPORT_WIDTH,
    height: int = DEFAULT_VIEWPORT_HEIGHT,
) -> list[CaptureResult]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - 依赖环境问题
        raise RuntimeError("当前环境未安装 Python Playwright。") from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            chromium_sandbox=False,
            args=[
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=1,
        )
        page = context.new_page()

        def render_page(task: CaptureTask) -> None:
            page.goto(task.html_path.resolve().as_uri(), wait_until="load")
            page.wait_for_timeout(300)
            page.screenshot(path=str(task.screenshot_path))

        try:
            return run_capture_tasks(tasks, capture_page=render_page, overwrite=overwrite)
        finally:
            context.close()
            browser.close()


def summarize_capture_results(results: list[CaptureResult]) -> dict[str, int]:
    summary = {"captured": 0, "skipped": 0, "failed": 0}
    for result in results:
        summary[result.status] += 1
    return summary
