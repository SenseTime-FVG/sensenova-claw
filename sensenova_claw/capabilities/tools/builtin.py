from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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
    description = "获取网页内容"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "method": {"type": "string", "default": "GET"},
        },
        "required": ["url"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        url = str(kwargs["url"])
        method = str(kwargs.get("method", "GET")).upper()
        timeout = config.get("tools.fetch_url.timeout", 15)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.request(method, url)
        text = resp.text
        # 内存保护截断：限制 HTTP 响应体大小，防止 OOM
        max_size = int(config.get("tools.fetch_url.max_response_mb", 10) * 1024 * 1024)
        if len(text) > max_size:
            text = text[:max_size]
        # 返回原始内容，由 ToolRuntime 层做 token 截断
        return {"url": str(resp.url), "status_code": resp.status_code, "content": text}


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

