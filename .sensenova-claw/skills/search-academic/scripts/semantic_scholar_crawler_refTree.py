#!/usr/bin/env python3
"""Fixed-flow Semantic Scholar crawler.

Usage:
    python3 semantic_scholar_crawler_refTree.py --query "Qwen Technical Report"

The script intentionally uses deterministic selectors and DOM extraction instead
of an LLM agent. It requires Playwright:
    python3 -m pip install playwright
    python3 -m playwright install firefox
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urljoin


BASE_URL = "https://www.semanticscholar.org"
DEFAULT_QUERY = "qwen technial report"


def parse_limit(value: str | None) -> int | None:
    if value is None or value == "":
        return 10
    if value.lower() == "all":
        return None
    try:
        limit = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--limit must be a positive integer or 'all'") from exc
    if limit <= 0:
        raise argparse.ArgumentTypeError("--limit must be a positive integer or 'all'")
    return limit


def ancestors_from(path: Path) -> list[Path]:
    resolved = path.resolve()
    start = resolved.parent if resolved.is_file() or resolved.suffix else resolved
    return [start, *start.parents]


def has_camoufox_js(directory: Path) -> bool:
    return (directory / "node_modules" / "camoufox-js").exists()


def find_upwards(start: Path) -> Path | None:
    for directory in ancestors_from(start):
        if has_camoufox_js(directory):
            return directory
    return None


def find_camoufox_project_root(
    script_path: Path | None = None,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> Path:
    env = env or os.environ
    script_path = script_path or Path(__file__)
    cwd = cwd or Path.cwd()

    npm_package_json = env.get("npm_package_json")
    candidates: list[Path] = []
    if npm_package_json:
        candidates.append(Path(npm_package_json))
    candidates.extend([script_path, cwd])

    for candidate in candidates:
        root = find_upwards(candidate)
        if root:
            return root

    raise SystemExit(
        "Could not find node_modules/camoufox-js. Search order:\n"
        "  1. npm_package_json directory and parents\n"
        "  2. crawler script directory and parents\n"
        "  3. current working directory and parents\n"
        "Run `npm install` in a directory that contains camoufox-js."
    )


def host_os_name() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform.startswith("win"):
        return "windows"
    return "macos"


def normalize_space(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def title_matches(title: str | None, query: str) -> bool:
    """Exact, case-sensitive title match after whitespace normalization."""
    return normalize_space(title) == normalize_space(query)


def absolute_url(href: str | None) -> str | None:
    if not href:
        return None
    return urljoin(BASE_URL, href)


def extract_quote_count(text: str | None) -> int | None:
    """Extract the number shown after the quote icon/marker in a paper card."""
    if not text:
        return None
    normalized = normalize_space(text)
    patterns = [
        r'["“”]\s*([0-9][0-9,]*)\b',
        r"\b([0-9][0-9,]*)\s+Citations?\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            return int(match.group(1).replace(",", ""))
    return None


def camoufox_launch_options_script(headless: bool, os_name: str | None = None) -> str:
    headless_js = "true" if headless else "false"
    os_js = json.dumps(os_name or host_os_name())
    return (
        "import { launchOptions } from 'camoufox-js';\n"
        f"const options = await launchOptions({{headless:{headless_js}, os:{os_js}, humanize:true, enable_cache:true}});\n"
        "console.log(JSON.stringify(options));\n"
    )


def camoufox_launch_options(headless: bool) -> dict[str, Any]:
    project_root = find_camoufox_project_root()
    try:
        raw = subprocess.check_output(
            ["node", "--input-type=module", "-e", camoufox_launch_options_script(headless=headless)],
            cwd=project_root,
            text=True,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise SystemExit("Node.js is required because this script reuses camoufox-js launchOptions().") from exc
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            "Failed to generate Camoufox launch options via camoufox-js.\n"
            f"stderr:\n{exc.stderr}"
        ) from exc
    return json.loads(raw)


async def create_page(headless: bool):
    try:
        from playwright.async_api import async_playwright
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Playwright is not installed. Run:\n"
            "  python3 -m pip install playwright\n"
            "  python3 -m playwright install firefox"
        ) from exc

    options = camoufox_launch_options(headless=headless)
    playwright = await async_playwright().start()
    browser = await playwright.firefox.launch(
        executable_path=options["executablePath"],
        headless=options.get("headless", headless),
        args=options.get("args") or [],
        env={**os.environ, **(options.get("env") or {})},
        firefox_user_prefs=options.get("firefoxUserPrefs") or {},
        proxy=options.get("proxy") or None,
    )
    context = await browser.new_context(
        viewport={"width": 1280, "height": 720},
        permissions=["geolocation"],
        locale="en-US",
        timezone_id="America/Los_Angeles",
        geolocation={"latitude": 37.7749, "longitude": -122.4194},
    )
    page = await context.new_page()
    return playwright, browser, context, page


async def dismiss_popups(page) -> None:
    for label in ["Accept", "I agree", "Got it", "Close"]:
        try:
            button = page.get_by_role("button", name=re.compile(rf"^{re.escape(label)}$", re.I))
            if await button.count():
                await button.first.click(timeout=1000)
        except Exception:
            pass


async def find_exact_search_result(page, query: str) -> dict[str, Any]:
    search_url = f"{BASE_URL}/search?q={quote_plus(query)}&sort=relevance"
    await page.goto(search_url, wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle", timeout=30000)
    await dismiss_popups(page)
    await page.wait_for_selector('a[href*="/paper/"]', timeout=30000)

    result = await page.evaluate(
        """(query) => {
            const normalize = (s) => (s || '').replace(/\\s+/g, ' ').trim();
            const anchors = [...document.querySelectorAll('a[href*="/paper/"]')];
            for (const a of anchors) {
                const title = normalize(a.innerText || a.textContent);
                if (title === normalize(query)) {
                    return {
                        title,
                        href: a.getAttribute('href'),
                        url: new URL(a.getAttribute('href'), location.origin).href,
                        text: normalize(a.closest('article, li, div')?.innerText || '')
                    };
                }
            }
            return null;
        }""",
        query,
    )
    if not result:
        visible_titles = await page.evaluate(
            """() => [...document.querySelectorAll('a[href*="/paper/"]')]
                .map(a => (a.innerText || a.textContent || '').replace(/\\s+/g, ' ').trim())
                .filter(Boolean)
                .slice(0, 20)"""
        )
        raise RuntimeError(
            f'No search result title exactly matched "{query}". '
            f"Visible paper titles: {visible_titles}"
        )
    return result


async def settle_list(page, limit: int | None, max_rounds: int = 40) -> None:
    previous = -1
    stable_rounds = 0
    for _ in range(max_rounds):
        count = await count_paper_links(page)
        if limit and count >= limit:
            return
        if count == previous:
            stable_rounds += 1
        else:
            stable_rounds = 0
            previous = count
        if stable_rounds >= 4:
            return
        await page.mouse.wheel(0, 1800)
        await page.wait_for_timeout(1000)
        await click_more_buttons(page)


async def click_more_buttons(page) -> None:
    for name in [r"Show More", r"Load More", r"More"]:
        try:
            button = page.get_by_role("button", name=re.compile(name, re.I))
            if await button.count():
                await button.last.click(timeout=1500)
                await page.wait_for_timeout(1000)
        except Exception:
            pass


async def count_paper_links(page) -> int:
    return await page.locator('a[href*="/paper/"]').count()


async def extract_paper_list(page, current_paper_url: str, limit: int | None, section_selector: str = "body") -> list[dict[str, Any]]:
    rows = await page.evaluate(
        """({ currentPaperUrl, sectionSelector }) => {
            const normalize = (s) => (s || '').replace(/\\s+/g, ' ').trim();
            const absolute = (href) => new URL(href, location.origin).href;
            const quoteCount = (text) => {
                const quoted = normalize(text).match(/["“”]\\s*([0-9][0-9,]*)\\b/i);
                if (quoted) return Number(quoted[1].replace(/,/g, ''));
                const citations = normalize(text).match(/\\b([0-9][0-9,]*)\\s+Citations?\\b/i);
                if (citations) return Number(citations[1].replace(/,/g, ''));
                return null;
            };

            const root = document.querySelector(sectionSelector);
            if (!root) return [];
            const seen = new Set();
            const papers = [];
            for (const card of [...root.querySelectorAll('.cl-paper-row.citation-list__paper-row')]) {
                const a = card.querySelector('a.link-button--show-visited[href*="/paper/"]');
                if (!a) continue;
                const title = normalize(a.innerText || a.textContent);
                const href = a.getAttribute('href');
                if (!title || !href || title.length < 3) continue;
                if (href.includes('/figure/')) continue;
                const url = absolute(href).split('#')[0];
                if (url === currentPaperUrl.split('#')[0]) continue;
                if (seen.has(url)) continue;
                seen.add(url);

                const cardText = normalize(card.innerText || card.textContent);
                const countLink = [...card.querySelectorAll('a.cl-paper-stats__citation-pdp-link')]
                    .map((link) => normalize(link.innerText || link.textContent))
                    .find((text) => /^[0-9][0-9,]*$/.test(text));
                papers.push({
                    title,
                    url,
                    href,
                    citation_count: countLink ? Number(countLink.replace(/,/g, '')) : quoteCount(cardText),
                    raw_text: cardText
                });
            }
            return papers;
        }""",
        {"currentPaperUrl": current_paper_url, "sectionSelector": section_selector},
    )

    cleaned: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for row in rows:
        url = row.get("url")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        info = parse_card_text(row.get("raw_text", ""), row.get("title", ""))
        cleaned.append(
            {
                "title": row.get("title"),
                "url": url,
                "citation_count": row.get("citation_count"),
                **info,
                "raw_text": row.get("raw_text"),
            }
        )
        if limit and len(cleaned) >= limit:
            break
    return cleaned


async def collect_paginated_section(
    page,
    section_selector: str,
    current_paper_url: str,
    limit: int | None,
    max_pages: int | None,
    label: str,
) -> list[dict[str, Any]]:
    await page.locator(section_selector).scroll_into_view_if_needed(timeout=30000)
    all_rows: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    page_index = 0

    while True:
        page_index += 1
        rows = await extract_paper_list(page, current_paper_url, limit=None, section_selector=section_selector)
        for row in rows:
            url = row.get("url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            all_rows.append(row)
            if limit and len(all_rows) >= limit:
                print(f"{label}: collected {len(all_rows)} rows", file=sys.stderr)
                return all_rows[:limit]

        if page_index == 1 or page_index % 10 == 0:
            print(f"{label}: page {page_index}, collected {len(all_rows)} rows", file=sys.stderr)

        if max_pages and page_index >= max_pages:
            print(f"{label}: stopped at max-pages={max_pages}, collected {len(all_rows)} rows", file=sys.stderr)
            return all_rows

        next_button = page.locator(f"{section_selector} button.cl-pager__next")
        if not await next_button.count():
            print(f"{label}: no next button, collected {len(all_rows)} rows", file=sys.stderr)
            return all_rows
        if await next_button.first.is_disabled():
            print(f"{label}: reached last page, collected {len(all_rows)} rows", file=sys.stderr)
            return all_rows

        previous_signature = "|".join((row.get("url") or "") for row in rows[:3])
        await next_button.first.scroll_into_view_if_needed(timeout=5000)
        await next_button.first.click(timeout=10000)
        await page.wait_for_timeout(1200)
        for _ in range(20):
            new_rows = await extract_paper_list(page, current_paper_url, limit=None, section_selector=section_selector)
            new_signature = "|".join((row.get("url") or "") for row in new_rows[:3])
            if new_signature and new_signature != previous_signature:
                break
            await page.wait_for_timeout(300)


def parse_card_text(raw_text: str, title: str) -> dict[str, Any]:
    lines = [normalize_space(line) for line in (raw_text or "").splitlines()]
    lines = [line for line in lines if line]
    compact = normalize_space(raw_text)
    year_match = re.search(r"\b(19|20)\d{2}\b", compact)
    return {
        "year": int(year_match.group(0)) if year_match else None,
        "authors": extract_authors(lines, title),
        "abstract_or_tldr": extract_tldr(compact),
    }


def extract_authors(lines: list[str], title: str) -> list[str]:
    for index, line in enumerate(lines):
        if normalize_space(line) == normalize_space(title) and index + 1 < len(lines):
            author_line = lines[index + 1]
            author_line = re.split(r"\bComputer Science\b|·|\b\d{4}\b", author_line)[0]
            return [part.strip() for part in re.split(r",|\s{2,}|\s+\+\d+\s+authors?", author_line) if part.strip()]
    return []


def extract_tldr(text: str) -> str | None:
    match = re.search(r"TLDR\s+(.*?)(?:Expand|Highly Influenced|PDF|Save|$)", text, flags=re.I)
    if match:
        return normalize_space(match.group(1))
    return None


async def crawl(query: str, output: Path, headless: bool, limit: int | None, max_pages: int | None) -> dict[str, Any]:
    playwright, browser, context, page = await create_page(headless=headless)
    try:
        matched = await find_exact_search_result(page, query)
        paper_url = matched["url"].split("#")[0]
        await browser.close()
        await playwright.stop()
        browser = None
        playwright = None

        references = await crawl_section(headless, paper_url, "#cited-papers", ".cited-papers", limit, max_pages, "references")
        citations = await crawl_section(headless, paper_url, "#citing-papers", ".citing-papers", limit, max_pages, "citations")

        result = {
            "query": query,
            "matched_paper": {
                "title": matched["title"],
                "url": paper_url,
                "search_result_text": matched.get("text"),
            },
            "citations_count": len(citations),
            "references_count": len(references),
            "citations": citations,
            "references": references,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    finally:
        if browser is not None:
            await browser.close()
        if playwright is not None:
            await playwright.stop()


async def crawl_section(
    headless: bool,
    paper_url: str,
    hash_fragment: str,
    section_selector: str,
    limit: int | None,
    max_pages: int | None,
    label: str,
) -> list[dict[str, Any]]:
    playwright, browser, context, page = await create_page(headless=headless)
    try:
        await page.goto(f"{paper_url}{hash_fragment}", wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle", timeout=30000)
        await dismiss_popups(page)
        return await collect_paginated_section(page, section_selector, paper_url, limit, max_pages, label)
    finally:
        await browser.close()
        await playwright.stop()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl Semantic Scholar citations and references for an exact paper title.")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Case-sensitive exact paper title to match.")
    parser.add_argument("--output", default=".tmp/semantic_scholar_output.json", help="JSON output path.")
    parser.add_argument("--limit", default="10", help="Maximum papers per list, or 'all'. Defaults to 10.")
    parser.add_argument("--max-pages", type=int, default=None, help="Maximum pages to collect per list.")
    parser.add_argument("--headless", choices=["true", "false"], default="true", help="Run Camoufox headless.")
    return parser.parse_args(argv)


def format_stdout_result(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    result = asyncio.run(
        crawl(
            query=args.query,
            output=Path(args.output),
            headless=args.headless == "true",
            limit=parse_limit(args.limit),
            max_pages=args.max_pages,
        )
    )
    print(format_stdout_result(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
