from __future__ import annotations

import asyncio
import mimetypes
import json
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

from sensenova_claw.platform.config.config import config
from sensenova_claw.capabilities.tools.base import Tool, ToolRiskLevel


def _empty_search_response(provider: str, query: str, note: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "query": query,
        "items": [],
        "note": note,
    }


def _clamp_search_limit(raw: Any, *, default: int, upper: int = 20) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, upper))


def _merge_snippets(primary: Any, extra_snippets: Any = None) -> str | None:
    parts: list[str] = []
    if primary:
        parts.append(str(primary))
    if isinstance(extra_snippets, list):
        parts.extend(str(item) for item in extra_snippets if item)
    return "\n".join(parts) if parts else None


def _normalize_search_item(
    *,
    title: Any,
    link: Any,
    snippet: Any,
    **extra: Any,
) -> dict[str, Any]:
    item = {
        "title": title,
        "link": link,
        "snippet": snippet,
    }
    for key, value in extra.items():
        if value not in (None, "", [], {}):
            item[key] = value
    return item


def _resolve_with_workdir(raw_path: str, agent_workdir: str | None) -> Path:
    """相对路径优先基于 agent workdir 解析，绝对路径直接返回。"""
    p = Path(raw_path).expanduser()
    if p.is_absolute():
        return p.resolve()
    if agent_workdir:
        return (Path(agent_workdir) / p).resolve()
    return p


def _resolve_bash_cwd(
    *,
    policy: Any,
    working_dir: Any,
    agent_workdir: str | None,
) -> tuple[str | None, dict[str, Any] | None]:
    """统一解析 bash_command 的 cwd，保证与 agent workdir 语义一致。"""
    from sensenova_claw.platform.security.path_policy import PathVerdict

    cwd_raw = str(working_dir) if working_dir else None
    resolved_cwd: Path | None = None
    if cwd_raw:
        resolved_cwd = _resolve_with_workdir(cwd_raw, agent_workdir)
    elif agent_workdir:
        resolved_cwd = Path(agent_workdir).expanduser().resolve()

    if policy:
        if resolved_cwd is None:
            return str(policy.workspace), None

        verdict = policy.check_cwd(str(resolved_cwd))
        blocked_path = cwd_raw or agent_workdir or str(resolved_cwd)
        if verdict == PathVerdict.DENY:
            return None, {"success": False, "error": f"系统目录禁止作为工作目录: {blocked_path}"}
        if verdict == PathVerdict.NEED_GRANT:
            return None, {
                "success": False,
                "error": f"该目录未授权，请先获得用户许可: {blocked_path}",
                "action": "need_grant",
                "path": blocked_path,
            }
        return str(policy.safe_resolve(str(resolved_cwd))), None

    if resolved_cwd is None:
        return ".", None
    return str(resolved_cwd), None


_FETCH_URL_ALLOWED_FORMATS = {"markdown", "text"}
_FETCH_URL_HTML_CANDIDATE_SELECTORS = (
    ".abstract",
    "#abstract",
    "[class*='abstract']",
    "[id*='abstract']",
    "blockquote.abstract",
    "article",
    "main",
    "[role='main']",
    ".main-content",
    ".page-main",
    ".page-content",
    ".content",
    ".post-content",
    ".entry-content",
    ".article-content",
)
_FETCH_URL_NOISE_KEYWORDS = (
    "breadcrumb",
    "cookie",
    "footer",
    "header",
    "menu",
    "nav",
    "newsletter",
    "promo",
    "recommend",
    "related",
    "share",
    "sidebar",
    "social",
    "subscribe",
)
_FETCH_URL_STOP_SECTION_KEYWORDS = (
    "about arxivlabs",
    "bibliographic",
    "cite as",
    "comments",
    "references",
    "related papers",
    "submission history",
    "subjects",
)


def _validate_fetch_url(raw_url: Any, raw_format: Any) -> tuple[str, str]:
    """校验 fetch_url 的入参，避免进入真实请求后才失败。"""
    url = str(raw_url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("fetch_url 的 url 必须以 http:// 或 https:// 开头")

    output_format = str(raw_format or "markdown").strip().lower() or "markdown"
    if output_format not in _FETCH_URL_ALLOWED_FORMATS:
        raise ValueError("fetch_url 的 format 仅支持 markdown 或 text")
    return url, output_format


def _normalize_fetch_content_type(raw_content_type: Any, body: bytes) -> str:
    """归一化 Content-Type，仅保留主 MIME type。"""
    normalized = str(raw_content_type or "").split(";", 1)[0].strip().lower()
    if normalized:
        return normalized

    sniff = body.lstrip()[:64].lower()
    if sniff.startswith((b"{", b"[")):
        return "application/json"
    if sniff.startswith((b"<!doctype html", b"<html", b"<body")):
        return "text/html"
    return "application/octet-stream"


def _truncate_fetch_text(text: str) -> str:
    """限制 fetch_url 返回的文本大小，避免单工具结果过大。"""
    max_size = int(config.get("tools.fetch_url.max_response_mb", 10) * 1024 * 1024)
    if len(text) > max_size:
        return text[:max_size]
    return text


def _looks_like_noise_element(tag: Any) -> bool:
    tag_name = getattr(tag, "name", None)
    if not tag_name:
        return False
    if tag_name in {"nav", "footer", "aside", "form"}:
        return True
    if tag_name == "header":
        return tag.find("h1") is None
    tag_attrs = getattr(tag, "attrs", None) or {}
    attrs: list[str] = []
    for key in ("class", "id", "role", "aria-label"):
        value = tag_attrs.get(key)
        if isinstance(value, list):
            attrs.extend(str(item).lower() for item in value)
        elif value:
            attrs.append(str(value).lower())
    haystack = " ".join(attrs)
    if "abstract" in haystack:
        return False
    if tag.find("h1"):
        return False
    return any(keyword in haystack for keyword in _FETCH_URL_NOISE_KEYWORDS)


def _is_link_heavy_noise(tag: Any) -> bool:
    """识别正文里的高链接密度导航块、侧边栏和推荐列表。"""
    tag_name = getattr(tag, "name", None)
    if not tag_name:
        return False
    if tag_name not in {"div", "section", "aside", "ul", "ol"}:
        return False
    text = tag.get_text(" ", strip=True)
    text_length = len(text)
    if text_length < 40:
        return False

    links = tag.find_all("a")
    link_count = len(links)
    if link_count < 4:
        return False

    link_text_length = sum(len(link.get_text(" ", strip=True)) for link in links)
    paragraph_count = len(tag.find_all("p"))
    heading_count = len(tag.find_all(["h1", "h2", "h3", "h4"]))
    link_ratio = link_text_length / max(text_length, 1)

    if paragraph_count == 0 and link_ratio >= 0.45:
        return True
    if heading_count == 0 and paragraph_count <= 1 and link_count >= 8:
        return True
    return False


def _score_html_candidate(node: Any) -> int:
    text_length = len(node.get_text(" ", strip=True))
    paragraph_count = len(node.find_all("p"))
    list_count = len(node.find_all("li"))
    links = node.find_all("a")
    link_count = len(links)
    link_text_length = sum(len(link.get_text(" ", strip=True)) for link in links)
    score = text_length + paragraph_count * 350 + list_count * 80
    score -= link_count * 120
    score -= link_text_length * 2
    if paragraph_count == 0 and list_count < 2:
        score -= 400
    attrs = " ".join(
        str(item).lower()
        for key in ("class", "id")
        for item in (
            getattr(node, "attrs", {}).get(key, [])
            if isinstance(getattr(node, "attrs", {}).get(key), list)
            else [getattr(node, "attrs", {}).get(key)]
        )
        if item
    )
    if "abstract" in attrs:
        score += 2500
    return score


def _find_heading_anchored_container(body: Any) -> Any | None:
    """优先围绕 h1 寻找最小正文容器，避免整页导航抢占候选。"""
    heading = body.find("h1")
    if not heading or len(heading.get_text(" ", strip=True)) < 12:
        return None

    fallback = None
    current = heading.parent
    while current and current != body:
        text_length = len(current.get_text(" ", strip=True))
        paragraphs = [
            paragraph.get_text(" ", strip=True)
            for paragraph in current.find_all("p")
        ]
        long_paragraphs = [paragraph for paragraph in paragraphs if len(paragraph) >= 80]
        links = current.find_all("a")
        link_text_length = sum(len(link.get_text(" ", strip=True)) for link in links)
        link_ratio = link_text_length / max(text_length, 1)

        if len(long_paragraphs) >= 2 and link_ratio <= 0.45 and text_length >= 200:
            return current
        if fallback is None and long_paragraphs and link_ratio <= 0.30 and text_length >= 160:
            fallback = current
        current = current.parent
    return fallback


def _normalize_markdown_text(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    normalized: list[str] = []
    blank_count = 0
    for line in lines:
        if not line.strip():
            blank_count += 1
            if blank_count <= 1:
                normalized.append("")
            continue
        blank_count = 0
        normalized.append(line)
    return "\n".join(normalized).strip()


def _normalize_plain_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    normalized: list[str] = []
    blank_count = 0
    for line in lines:
        if not line:
            blank_count += 1
            if blank_count <= 1:
                normalized.append("")
            continue
        blank_count = 0
        normalized.append(line)
    return "\n".join(normalized).strip()


def _matches_stop_section(text: str) -> bool:
    normalized = " ".join(str(text or "").lower().split())
    return any(keyword in normalized for keyword in _FETCH_URL_STOP_SECTION_KEYWORDS)


def _prune_stop_sections(fragment: Any) -> None:
    for tag in list(fragment.find_all(["h2", "h3", "h4", "strong", "dt", "summary"])):
        text = tag.get_text(" ", strip=True)
        if not _matches_stop_section(text):
            continue
        current = tag
        while getattr(current, "parent", None) is not None and current.parent != fragment:
            if getattr(current.parent, "name", None) in {"article", "main", "section", "div", "aside"}:
                current = current.parent
                break
            current = current.parent
        current.decompose()


def _prepend_primary_heading(fragment: Any, body: Any) -> None:
    if fragment.find("h1"):
        return
    heading = body.find("h1")
    if not heading:
        return
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return
    heading_fragment = BeautifulSoup(str(heading), "html.parser")
    first_heading = heading_fragment.find("h1")
    if not first_heading:
        return
    container = fragment.body or fragment
    if getattr(container, "contents", None):
        container.insert(0, "\n")
        container.insert(0, first_heading)
    else:
        container.append(first_heading)


def _extract_primary_heading_text(body: Any) -> str:
    heading = body.find("h1")
    if not heading:
        return ""
    return heading.get_text(" ", strip=True)


def _extract_error_html_content(html: str, output_format: str) -> str:
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return _fallback_extract_html_content(html, output_format)

    soup = BeautifulSoup(html, "html.parser")
    title = ""
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(" ", strip=True)
    heading = soup.find("h1")
    heading_text = heading.get_text(" ", strip=True) if heading else ""
    paragraphs: list[str] = []
    for paragraph in soup.find_all("p"):
        text = paragraph.get_text(" ", strip=True)
        if text and len(text) >= 12:
            paragraphs.append(text)
        if len(paragraphs) >= 2:
            break

    parts: list[str] = []
    primary_title = heading_text or title
    if output_format == "markdown" and primary_title:
        parts.append(f"# {primary_title}")
    elif primary_title:
        parts.append(primary_title)
    if title and title != primary_title:
        parts.append(title)
    parts.extend(paragraphs)
    summary = "\n\n".join(part for part in parts if part).strip()
    if summary:
        return summary
    return _fallback_extract_html_content(html, output_format)


def _fallback_extract_html_content(html: str, output_format: str) -> str:
    """HTML 结构化提取失败时，回退到较保守的纯文本清洗。"""
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?is)<noscript.*?>.*?</noscript>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    cleaned = _normalize_plain_text(text)
    if output_format == "markdown":
        return cleaned
    return cleaned


def _extract_html_content(html: str, output_format: str) -> str:
    """抽取 HTML 正文，并按目标格式输出。"""
    try:
        from bs4 import BeautifulSoup, Comment
        from markdownify import markdownify as to_markdown
    except Exception:
        return _fallback_extract_html_content(html, output_format)

    try:
        soup = BeautifulSoup(html, "html.parser")

        for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
            comment.extract()
        for tag in soup.find_all(["script", "style", "noscript", "svg"]):
            tag.decompose()

        for tag in list(soup.find_all(True)):
            if _looks_like_noise_element(tag) or _is_link_heavy_noise(tag):
                tag.decompose()

        body = soup.body or soup
        candidates: list[tuple[int, Any]] = []
        anchored = _find_heading_anchored_container(body)
        if anchored is not None:
            candidates.append((_score_html_candidate(anchored) + 8000, anchored))

        for selector in _FETCH_URL_HTML_CANDIDATE_SELECTORS:
            for node in body.select(selector):
                text_length = len(node.get_text(" ", strip=True))
                if text_length >= 80:
                    score = _score_html_candidate(node)
                    candidates.append((score, node))

        if not candidates:
            for node in body.find_all(["article", "main", "section", "div"]):
                text_length = len(node.get_text(" ", strip=True))
                paragraph_count = len(node.find_all(["p", "li"]))
                if text_length >= 120 and paragraph_count >= 1:
                    score = _score_html_candidate(node)
                    candidates.append((score, node))

        container = max(candidates, key=lambda item: item[0])[1] if candidates else body
        fragment = BeautifulSoup(str(container), "html.parser")
        _prepend_primary_heading(fragment, body)
        for tag in list(fragment.find_all(True)):
            if _looks_like_noise_element(tag) or _is_link_heavy_noise(tag):
                tag.decompose()
        _prune_stop_sections(fragment)
        primary_heading = _extract_primary_heading_text(body)

        if output_format == "markdown":
            markdown = to_markdown(
                str(fragment),
                heading_style="ATX",
                bullets="-",
                strip=["script", "style", "noscript", "svg"],
            )
            normalized = _normalize_markdown_text(markdown)
            if primary_heading and primary_heading not in normalized:
                normalized = _normalize_markdown_text(f"# {primary_heading}\n\n{normalized}")
            if normalized:
                return normalized
        else:
            plain_text = fragment.get_text("\n", strip=True)
            normalized = _normalize_plain_text(plain_text)
            if primary_heading and primary_heading not in normalized:
                normalized = _normalize_plain_text(f"{primary_heading}\n\n{normalized}")
            if normalized:
                return normalized
    except Exception:
        pass

    return _fallback_extract_html_content(html, output_format)


def _extract_download_filename(headers: Any, url: str, content_type: str) -> str:
    """优先从响应头提取下载文件名，失败时回退到 URL。"""
    disposition = str(getattr(headers, "get", lambda *_: "")("Content-Disposition", "") or "")
    file_name = ""

    match = re.search(r"filename\*\s*=\s*UTF-8''([^;]+)", disposition, flags=re.IGNORECASE)
    if match:
        file_name = unquote(match.group(1).strip())
    else:
        match = re.search(r'filename\s*=\s*"([^"]+)"', disposition, flags=re.IGNORECASE)
        if match:
            file_name = match.group(1).strip()
        else:
            match = re.search(r"filename\s*=\s*([^;]+)", disposition, flags=re.IGNORECASE)
            if match:
                file_name = match.group(1).strip().strip('"')

    if not file_name:
        file_name = Path(urlparse(url).path).name

    file_name = Path(file_name).name.strip() or "download"
    file_name = re.sub(r"[^A-Za-z0-9._-]+", "_", file_name)
    if "." not in file_name:
        suffix = mimetypes.guess_extension(content_type or "") or ".bin"
        file_name = f"{file_name}{suffix}"
    return file_name


def _save_downloaded_binary(
    *,
    data: bytes,
    file_name: str,
    session_id: str,
    agent_id: str | None = None,
) -> Path:
    """保存非文本响应到当前 session 的附件目录。"""
    from sensenova_claw.platform.config.workspace import (
        resolve_sensenova_claw_home,
        resolve_session_artifact_dir,
    )

    home = resolve_sensenova_claw_home(config)
    safe_session_id = str(session_id or "").strip() or "fetch_url_default"
    artifact_dir = resolve_session_artifact_dir(home, safe_session_id, agent_id=agent_id)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    target = artifact_dir / file_name
    stem = target.stem
    suffix = target.suffix
    counter = 1
    while target.exists():
        target = artifact_dir / f"{stem}_{counter}{suffix}"
        counter += 1

    target.write_bytes(data)
    return target


class BashCommandTool(Tool):
    name = "bash_command"
    description = "执行 shell 命令"
    risk_level = ToolRiskLevel.HIGH
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的命令"},
            "working_dir": {"type": "string", "description": "工作目录"},
        },
        "required": ["command"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        kwargs.pop("_path_policy", None)
        agent_workdir: str | None = kwargs.pop("_agent_workdir", None)
        command = str(kwargs.get("command", ""))
        cwd_raw = kwargs.get("working_dir")
        cwd = cwd_raw or agent_workdir or "."

        def _run() -> dict[str, Any]:
            proc = subprocess.run(
                command,
                cwd=cwd,
                shell=True,
                capture_output=True,
                timeout=300,
            )
            return {
                "return_code": proc.returncode,
                "stdout": proc.stdout.decode("utf-8", errors="replace"),
                "stderr": proc.stderr.decode("utf-8", errors="replace"),
            }

        return await asyncio.to_thread(_run)


class SerperSearchTool(Tool):
    name = "serper_search"
    description = "使用 Serper API 搜索网络信息"
    parameters = {
        "type": "object",
        "properties": {
            "q": {"type": "string", "description": "搜索关键词"},
            "tbs": {"type": "string", "description": "时间过滤 h/d/m/y"},
            "page": {"type": "integer", "description": "页码，默认1"},
        },
        "required": ["q"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        api_key = config.get("tools.serper_search.api_key", "")
        q = str(kwargs.get("q", ""))
        page = int(kwargs.get("page", 1))
        tbs = kwargs.get("tbs")
        limit = _clamp_search_limit(
            kwargs.get("max_results", config.get("tools.serper_search.max_results", 10)),
            default=int(config.get("tools.serper_search.max_results", 10)),
        )

        if not api_key:
            return _empty_search_response("serper", q, "SERPER_API_KEY 未配置，返回空结果")

        payload: dict[str, Any] = {"q": q, "gl": "cn", "hl": "zh-cn", "page": page}
        if tbs:
            payload["tbs"] = f"qdr:{tbs}"

        headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=config.get("tools.serper_search.timeout", 15)) as client:
            resp = await client.post("https://google.serper.dev/search", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        organic = data.get("organic", [])[:limit]
        return {
            "provider": "serper",
            "query": q,
            "page": page,
            "items": [
                _normalize_search_item(
                    title=item.get("title"),
                    link=item.get("link"),
                    snippet=item.get("snippet"),
                )
                for item in organic
            ],
        }


class ImageSearchTool(Tool):
    name = "image_search"
    description = "使用 Serper Images API 搜索图片候选"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "图片搜索关键词"},
            "top_k": {"type": "integer", "description": "返回候选图片数量，默认使用配置"},
        },
        "required": ["query"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        query = str(kwargs.get("query") or kwargs.get("q") or "").strip()
        if not query:
            return {"success": False, "error": "query 不能为空"}

        api_key = config.get("tools.image_search.api_key", "") or config.get("tools.serper_search.api_key", "")
        top_k = _clamp_search_limit(
            kwargs.get("top_k", config.get("tools.image_search.top_k", 10)),
            default=int(config.get("tools.image_search.top_k", 10)),
        )

        if not api_key:
            result = _empty_search_response("serper_images", query, "SERPER_API_KEY 未配置，返回空结果")
            result["results"] = []
            result["top_k"] = top_k
            return result

        payload: dict[str, Any] = {"q": query}
        if any("\u4E00" <= char <= "\u9FFF" for char in query):
            payload.update({"gl": "cn", "hl": "zh-cn"})
        else:
            payload.update({"gl": "us", "hl": "en"})

        headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=config.get("tools.image_search.timeout", 30)) as client:
            resp = await client.post("https://google.serper.dev/images", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        results: list[dict[str, Any]] = []
        items: list[dict[str, Any]] = []
        for item in data.get("images", [])[:top_k]:
            if not isinstance(item, dict):
                continue
            image_url = item.get("imageUrl") or item.get("image_url") or item.get("original")
            if not image_url:
                continue
            source_page = item.get("link") or item.get("sourceUrl") or ""
            source_domain = urlparse(source_page).netloc if source_page else ""
            result_item = {
                "title": item.get("title", ""),
                "image_url": image_url,
                "source_page": source_page,
                "source_domain": source_domain,
                "thumbnail_url": item.get("thumbnailUrl", ""),
                "width": item.get("imageWidth"),
                "height": item.get("imageHeight"),
            }
            results.append(result_item)
            items.append(
                _normalize_search_item(
                    title=item.get("title", ""),
                    link=source_page or image_url,
                    snippet=item.get("title", ""),
                    image_url=image_url,
                    source_page=source_page,
                    source_domain=source_domain,
                    thumbnail_url=item.get("thumbnailUrl"),
                    width=item.get("imageWidth"),
                    height=item.get("imageHeight"),
                )
            )

        return {
            "provider": "serper_images",
            "query": query,
            "top_k": top_k,
            "results": results,
            "items": items,
        }


class BraveSearchTool(Tool):
    name = "brave_search"
    description = "使用 Brave Search API 搜索网络信息"
    parameters = {
        "type": "object",
        "properties": {
            "q": {"type": "string", "description": "搜索关键词"},
            "page": {"type": "integer", "description": "页码，默认1"},
            "count": {"type": "integer", "description": "返回结果数，默认使用配置"},
            "freshness": {"type": "string", "description": "时间过滤，如 pd/pw/pm/py"},
            "country": {"type": "string", "description": "国家代码，如 US/CN"},
            "search_lang": {"type": "string", "description": "搜索语言，如 en/zh-hans"},
            "ui_lang": {"type": "string", "description": "界面语言，如 en-US/zh-CN"},
            "extra_snippets": {"type": "boolean", "description": "是否返回额外摘要"},
        },
        "required": ["q"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        api_key = config.get("tools.brave_search.api_key", "")
        q = str(kwargs.get("q", ""))
        page = _clamp_search_limit(kwargs.get("page", 1), default=1, upper=10)
        count = _clamp_search_limit(
            kwargs.get("count", config.get("tools.brave_search.max_results", 10)),
            default=int(config.get("tools.brave_search.max_results", 10)),
        )

        if not api_key:
            return _empty_search_response("brave", q, "BRAVE_SEARCH_API_KEY 未配置，返回空结果")

        params: dict[str, Any] = {
            "q": q,
            "count": count,
            "offset": page - 1,
            "country": kwargs.get("country") or config.get("tools.brave_search.country", "US"),
            "search_lang": kwargs.get("search_lang") or config.get("tools.brave_search.search_lang", "en"),
            "ui_lang": kwargs.get("ui_lang") or config.get("tools.brave_search.ui_lang", "en-US"),
        }
        freshness = kwargs.get("freshness")
        if freshness:
            params["freshness"] = str(freshness)

        if bool(kwargs.get("extra_snippets", config.get("tools.brave_search.extra_snippets", False))):
            params["extra_snippets"] = "true"

        headers = {
            "X-Subscription-Token": api_key,
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=config.get("tools.brave_search.timeout", 15)) as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers=headers,
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

        query_meta = data.get("query", {})
        results = data.get("web", {}).get("results", [])[:count]
        return {
            "provider": "brave",
            "query": query_meta.get("original", q),
            "page": page,
            "more_results_available": bool(query_meta.get("more_results_available", False)),
            "items": [
                _normalize_search_item(
                    title=item.get("title"),
                    link=item.get("url"),
                    snippet=_merge_snippets(item.get("description"), item.get("extra_snippets")),
                    language=item.get("language"),
                    age=item.get("age"),
                )
                for item in results
            ],
        }


class BaiduSearchTool(Tool):
    name = "baidu_search"
    description = "使用百度 AppBuilder AI Search 搜索网页信息"
    parameters = {
        "type": "object",
        "properties": {
            "q": {"type": "string", "description": "搜索关键词"},
            "max_results": {"type": "integer", "description": "返回结果数，默认使用配置"},
            "search_source": {"type": "string", "description": "搜索源，默认 baidu_search_v2"},
            "search_recency_filter": {"type": "string", "description": "时间过滤，如 day/week/month/year"},
        },
        "required": ["q"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        api_key = config.get("tools.baidu_search.api_key", "")
        q = str(kwargs.get("q", ""))
        limit = _clamp_search_limit(
            kwargs.get("max_results", config.get("tools.baidu_search.max_results", 10)),
            default=int(config.get("tools.baidu_search.max_results", 10)),
            upper=50,
        )

        if not api_key:
            return _empty_search_response("baidu", q, "BAIDU_APPBUILDER_API_KEY 未配置，返回空结果")

        payload: dict[str, Any] = {
            "messages": [{"role": "user", "content": q}],
            "search_source": kwargs.get("search_source") or config.get("tools.baidu_search.search_source", "baidu_search_v2"),
            "resource_type_filter": [{"type": "web", "top_k": limit}],
        }
        search_recency_filter = kwargs.get("search_recency_filter") or config.get(
            "tools.baidu_search.search_recency_filter",
            "",
        )
        if search_recency_filter:
            payload["search_recency_filter"] = str(search_recency_filter)

        headers = {
            "X-Appbuilder-Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=config.get("tools.baidu_search.timeout", 15)) as client:
            resp = await client.post(
                "https://qianfan.baidubce.com/v2/ai_search/web_search",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("code"):
            return {
                "provider": "baidu",
                "query": q,
                "items": [],
                "request_id": data.get("request_id"),
                "error_code": data.get("code"),
                "error": data.get("message", "百度搜索请求失败"),
            }

        references = data.get("references", [])
        web_results = [item for item in references if item.get("type") in (None, "web")]
        return {
            "provider": "baidu",
            "query": q,
            "request_id": data.get("request_id"),
            "items": [
                _normalize_search_item(
                    title=item.get("title"),
                    link=item.get("url"),
                    snippet=item.get("content"),
                    date=item.get("date"),
                    website=item.get("website"),
                    authority_score=item.get("authority_score"),
                    rerank_score=item.get("rerank_score"),
                )
                for item in web_results[:limit]
            ],
        }


class TavilySearchTool(Tool):
    name = "tavily_search"
    description = "使用 Tavily Search API 搜索网络信息"
    parameters = {
        "type": "object",
        "properties": {
            "q": {"type": "string", "description": "搜索关键词"},
            "search_depth": {"type": "string", "description": "搜索深度，如 basic/advanced/fast/ultra-fast"},
            "topic": {"type": "string", "description": "主题，如 general/news/finance"},
            "time_range": {"type": "string", "description": "时间范围，如 day/week/month/year"},
            "max_results": {"type": "integer", "description": "返回结果数，默认使用配置"},
        },
        "required": ["q"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        api_key = config.get("tools.tavily_search.api_key", "")
        q = str(kwargs.get("q", ""))
        limit = _clamp_search_limit(
            kwargs.get("max_results", config.get("tools.tavily_search.max_results", 5)),
            default=int(config.get("tools.tavily_search.max_results", 5)),
        )

        if not api_key:
            return _empty_search_response("tavily", q, "TAVILY_API_KEY 未配置，返回空结果")

        payload: dict[str, Any] = {
            "query": q,
            "search_depth": kwargs.get("search_depth") or config.get("tools.tavily_search.search_depth", "basic"),
            "topic": kwargs.get("topic") or config.get("tools.tavily_search.topic", "general"),
            "max_results": limit,
        }
        time_range = kwargs.get("time_range") or config.get("tools.tavily_search.time_range", "")
        if time_range:
            payload["time_range"] = str(time_range)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        project_id = config.get("tools.tavily_search.project_id", "")
        if project_id:
            headers["X-Project-ID"] = project_id

        async with httpx.AsyncClient(timeout=config.get("tools.tavily_search.timeout", 15)) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        result: dict[str, Any] = {
            "provider": "tavily",
            "query": data.get("query", q),
            "response_time": data.get("response_time"),
            "request_id": data.get("request_id"),
            "items": [
                _normalize_search_item(
                    title=item.get("title"),
                    link=item.get("url"),
                    snippet=item.get("content"),
                    score=item.get("score"),
                    favicon=item.get("favicon"),
                )
                for item in data.get("results", [])[:limit]
            ],
        }
        if data.get("answer"):
            result["answer"] = data.get("answer")
        return result


class FetchUrlTool(Tool):
    name = "fetch_url"
    description = "获取指定 URL 的网页内容，适合用来读取和分析网页内容，内容过大时，返回结果会截断并将完整内容存入文件。"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "format": {
                "type": "string",
                "enum": ["markdown", "text"],
                "default": "markdown",
                "description": "输出格式：markdown 保留标题/链接/列表等基础结构，text 返回纯文本",
            },
        },
        "required": ["url"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        url, output_format = _validate_fetch_url(kwargs.get("url"), kwargs.get("format", "markdown"))
        timeout = config.get("tools.fetch_url.timeout", 15)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url)

        body = bytes(resp.content or b"")
        content_type = _normalize_fetch_content_type(resp.headers.get("Content-Type", ""), body)
        result: dict[str, Any] = {
            "url": str(resp.url),
            "status_code": resp.status_code,
            "content_type": content_type,
            "format": output_format,
        }

        if resp.status_code < 200 or resp.status_code >= 300:
            detail = ""
            if content_type in {"text/html", "application/xhtml+xml"}:
                detail = _extract_error_html_content(resp.text, output_format)
            elif content_type == "application/json" or content_type.endswith("+json"):
                try:
                    detail = json.dumps(resp.json(), ensure_ascii=False, indent=2)
                except Exception:
                    detail = resp.text
            elif content_type.startswith("text/"):
                detail = resp.text
            else:
                detail = f"响应类型: {content_type}"
            detail = _truncate_fetch_text(str(detail).strip())
            message = f"fetch_url 请求失败 ({resp.status_code})"
            if detail:
                message = f"{message}: {detail}"
            raise ValueError(message)

        if content_type == "application/json" or content_type.endswith("+json"):
            try:
                json_payload = resp.json()
            except Exception as exc:
                raise ValueError(f"fetch_url 无法解析 JSON 响应: {exc}") from exc
            result["content"] = _truncate_fetch_text(
                json.dumps(json_payload, ensure_ascii=False, indent=2)
            )
            return result

        if content_type in {"text/html", "application/xhtml+xml"}:
            result["content"] = _truncate_fetch_text(_extract_html_content(resp.text, output_format))
            return result

        if content_type == "text/plain":
            result["content"] = _truncate_fetch_text(resp.text)
            return result

        if content_type == "text/markdown":
            text = resp.text
            if output_format == "text":
                text = _normalize_plain_text(text)
            result["content"] = _truncate_fetch_text(text)
            return result

        if content_type.startswith("text/"):
            result["content"] = _truncate_fetch_text(resp.text)
            return result

        download_name = _extract_download_filename(resp.headers, str(resp.url), content_type)
        download_path = _save_downloaded_binary(
            data=body,
            file_name=download_name,
            session_id=str(kwargs.get("_session_id", "")).strip(),
            agent_id=str(kwargs.get("_source_agent_id", "")).strip() or None,
        )
        summary = (
            f"已下载非文本内容: {content_type}, 文件名: {download_name}, "
            f"大小: {len(body)} bytes, 保存路径: {download_path}"
        )
        result.update({
            "download_path": str(download_path),
            "download_filename": download_name,
            "summary": summary,
            "content": summary,
        })
        return result


class ReadFileTool(Tool):
    name = "read_file"
    description = "读取文本文件"
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "encoding": {"type": "string", "default": "utf-8"},
            "start_line": {"type": "integer", "default": 1},
            "num_lines": {"type": "integer"},
        },
        "required": ["file_path"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        kwargs.pop("_path_policy", None)
        agent_workdir: str | None = kwargs.pop("_agent_workdir", None)
        raw_path = str(kwargs["file_path"])

        file_path = _resolve_with_workdir(raw_path, agent_workdir)

        if not file_path.exists():
            return {"success": False, "error": f"文件不存在: {file_path}"}

        encoding = str(kwargs.get("encoding", "utf-8"))
        start_line = int(kwargs.get("start_line", 1))
        num_lines = kwargs.get("num_lines")
        lines = file_path.read_text(encoding=encoding).splitlines()
        start = max(start_line - 1, 0)
        end = None if num_lines is None else start + int(num_lines)
        selected = lines[start:end]
        return {"file_path": str(file_path), "content": "\n".join(selected)}


class WriteFileTool(Tool):
    name = "write_file"
    description = "写入文本文件，支持全量覆盖、追加、插入、或替换指定行范围"
    risk_level = ToolRiskLevel.MEDIUM
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "要写入的内容"},
            "mode": {
                "type": "string",
                "enum": ["write", "append", "insert"],
                "default": "write",
                "description": "write=覆盖全文, append=追加到末尾, insert=在start_line处插入或替换",
            },
            "start_line": {
                "type": "integer",
                "description": "起始行号（从1开始），仅 mode=insert 时有效",
            },
            "end_line": {
                "type": "integer",
                "description": "结束行号（包含），仅 mode=insert 时有效。"
                "省略时为纯插入（原内容下移）；"
                "指定时替换 start_line 到 end_line 的内容",
            },
        },
        "required": ["file_path", "content"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        kwargs.pop("_path_policy", None)
        agent_workdir: str | None = kwargs.pop("_agent_workdir", None)
        raw_path = str(kwargs["file_path"])

        file_path = _resolve_with_workdir(raw_path, agent_workdir)

        file_path.parent.mkdir(parents=True, exist_ok=True)
        content = str(kwargs.get("content", ""))
        mode = str(kwargs.get("mode", "write"))
        start_line = kwargs.get("start_line")
        end_line = kwargs.get("end_line")

        if mode == "append":
            # 追加到文件末尾
            with file_path.open("a", encoding="utf-8") as f:
                f.write(content)

        elif mode == "insert" and start_line is not None:
            if not file_path.exists():
                # 文件不存在时等同于 write
                file_path.write_text(content, encoding="utf-8")
            else:
                lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
                idx = max(int(start_line) - 1, 0)
                new_lines = content.splitlines(keepends=True)
                # 确保 content 末尾换行符被保留
                if content and not content.endswith("\n") and new_lines:
                    pass  # splitlines(keepends=True) 已处理
                elif content.endswith("\n") and (not new_lines or not new_lines[-1].endswith("\n")):
                    new_lines.append("")

                if end_line is not None:
                    # 替换模式：删除 [start_line, end_line] 范围的行，插入新内容
                    end_idx = min(int(end_line), len(lines))
                    lines[idx:end_idx] = new_lines
                else:
                    # 纯插入模式：在 start_line 之前插入，原内容下移
                    lines[idx:idx] = new_lines

                file_path.write_text("".join(lines), encoding="utf-8")

        else:
            # 默认全量覆盖
            file_path.write_text(content, encoding="utf-8")

        return {"success": True, "file_path": str(file_path), "size": len(content), "mode": mode}


# ── Todolist 专用工具 ──────────────────────────────────────────


def _todolist_dir_from_config() -> Path:
    """获取 todolist 目录，不存在则创建。"""
    from sensenova_claw.platform.config.workspace import resolve_sensenova_claw_home
    home = resolve_sensenova_claw_home(config)
    d = home / "todolist"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _todolist_file(directory: Path, date_str: str) -> Path:
    return directory / f"todolist_{date_str}.json"


def _load_todolist_day(directory: Path, date_str: str) -> dict:
    fp = _todolist_file(directory, date_str)
    if fp.exists():
        with open(fp, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"date": date_str, "items": []}


def _save_todolist_day(directory: Path, date_str: str, data: dict) -> None:
    fp = _todolist_file(directory, date_str)
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def _publish_todolist_event(event_bus: Any, date_str: str, action: str) -> None:
    """向事件总线发布 todolist 变更事件"""
    if not event_bus:
        return
    from sensenova_claw.kernel.events.envelope import EventEnvelope
    from sensenova_claw.kernel.events.types import TODOLIST_UPDATED, SYSTEM_SESSION_ID
    await event_bus.publish(EventEnvelope(
        type=TODOLIST_UPDATED,
        session_id=SYSTEM_SESSION_ID,
        source="tool",
        payload={"date": date_str, "action": action},
    ))


class ManageTodolistTool(Tool):
    name = "manage_todolist"
    description = (
        "管理个人待办事项。支持 add(新增)、complete(完成/标记已完成)、update(更新)、"
        "toggle(切换完成/未完成状态)、delete(永久删除)、list(列出) 操作。"
        "注意：用户说「完成」「做完了」时应使用 complete，不要使用 delete。"
        "delete 仅用于用户明确要求「删除」「移除」待办时。"
    )
    risk_level = ToolRiskLevel.LOW
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "complete", "update", "toggle", "delete", "list"],
                "description": (
                    "操作类型：add=新增, complete=标记为已完成(设置status=done), "
                    "update=更新属性, toggle=切换完成/未完成, delete=永久删除, list=列出"
                ),
            },
            "date": {
                "type": "string",
                "description": "日期 YYYY-MM-DD，默认今天",
            },
            "title": {
                "type": "string",
                "description": "待办标题（add 必填）",
            },
            "item_id": {
                "type": "string",
                "description": "待办 ID（update/toggle/delete 时需要）",
            },
            "priority": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "优先级，默认 medium",
            },
            "due_date": {
                "type": "string",
                "description": "截止日期 YYYY-MM-DD",
            },
            "status": {
                "type": "string",
                "enum": ["todo", "done"],
                "description": "状态（update 时可指定）",
            },
        },
        "required": ["action"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        import uuid
        from datetime import datetime, date as date_mod

        event_bus = kwargs.pop("_event_bus", None)
        kwargs.pop("_agent_workdir", None)
        kwargs.pop("_path_policy", None)
        kwargs.pop("_session_id", None)
        kwargs.pop("_agent_registry", None)
        kwargs.pop("_ask_user_handler", None)
        kwargs.pop("_source_agent_id", None)
        kwargs.pop("_turn_id", None)
        kwargs.pop("_tool_call_id", None)

        action = str(kwargs.get("action", ""))
        date_str = str(kwargs.get("date", "")) or date_mod.today().isoformat()

        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return {"success": False, "error": f"日期格式错误，需要 YYYY-MM-DD，收到: {date_str}"}

        d = _todolist_dir_from_config()
        data = _load_todolist_day(d, date_str)

        if action == "list":
            data["items"].sort(key=lambda x: int(x.get("order", 0)))
            return {"success": True, "date": date_str, "items": data["items"]}

        if action == "add":
            title = str(kwargs.get("title", "")).strip()
            if not title:
                return {"success": False, "error": "add 操作需要 title"}
            item = {
                "id": str(uuid.uuid4()),
                "title": title,
                "priority": str(kwargs.get("priority", "medium")),
                "due_date": kwargs.get("due_date"),
                "status": "todo",
                "order": len(data["items"]),
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "completed_at": None,
            }
            data["items"].append(item)
            _save_todolist_day(d, date_str, data)
            await _publish_todolist_event(event_bus, date_str, "add")
            return {"success": True, "item": item}

        if action == "complete":
            item_id = str(kwargs.get("item_id", ""))
            for item in data["items"]:
                if item["id"] == item_id:
                    if item["status"] != "done":
                        item["status"] = "done"
                        item["completed_at"] = datetime.now().isoformat(timespec="seconds")
                        _save_todolist_day(d, date_str, data)
                        await _publish_todolist_event(event_bus, date_str, "complete")
                    return {"success": True, "item": item}
            return {"success": False, "error": f"待办项 '{item_id}' 不存在"}

        if action == "toggle":
            item_id = str(kwargs.get("item_id", ""))
            for item in data["items"]:
                if item["id"] == item_id:
                    old_status = item["status"]
                    item["status"] = "done" if old_status == "todo" else "todo"
                    if item["status"] == "done":
                        item["completed_at"] = datetime.now().isoformat(timespec="seconds")
                    else:
                        item["completed_at"] = None
                    _save_todolist_day(d, date_str, data)
                    await _publish_todolist_event(event_bus, date_str, "toggle")
                    return {"success": True, "item": item}
            return {"success": False, "error": f"待办项 '{item_id}' 不存在"}

        if action == "update":
            item_id = str(kwargs.get("item_id", ""))
            for item in data["items"]:
                if item["id"] == item_id:
                    if kwargs.get("title"):
                        item["title"] = str(kwargs["title"])
                    if kwargs.get("priority"):
                        item["priority"] = str(kwargs["priority"])
                    if "due_date" in kwargs:
                        item["due_date"] = kwargs["due_date"]
                    if kwargs.get("status"):
                        old_status = item["status"]
                        item["status"] = str(kwargs["status"])
                        if item["status"] == "done" and old_status != "done":
                            item["completed_at"] = datetime.now().isoformat(timespec="seconds")
                        elif item["status"] == "todo":
                            item["completed_at"] = None
                    _save_todolist_day(d, date_str, data)
                    await _publish_todolist_event(event_bus, date_str, "update")
                    return {"success": True, "item": item}
            return {"success": False, "error": f"待办项 '{item_id}' 不存在"}

        if action == "delete":
            item_id = str(kwargs.get("item_id", ""))
            original_len = len(data["items"])
            data["items"] = [i for i in data["items"] if i["id"] != item_id]
            if len(data["items"]) == original_len:
                return {"success": False, "error": f"待办项 '{item_id}' 不存在"}
            for idx, item in enumerate(data["items"]):
                item["order"] = idx
            _save_todolist_day(d, date_str, data)
            await _publish_todolist_event(event_bus, date_str, "delete")
            return {"success": True, "deleted": item_id}

        return {"success": False, "error": f"未知操作: {action}"}
