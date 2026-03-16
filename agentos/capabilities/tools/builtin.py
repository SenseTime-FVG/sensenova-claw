from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

import httpx

from agentos.platform.config.config import config
from agentos.capabilities.tools.base import Tool, ToolRiskLevel


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
        from agentos.platform.security.path_policy import PathPolicy, PathVerdict

        policy: PathPolicy | None = kwargs.pop("_path_policy", None)
        command = str(kwargs.get("command", ""))
        cwd_raw = kwargs.get("working_dir")

        if policy:
            if cwd_raw:
                verdict = policy.check_cwd(cwd_raw)
                if verdict == PathVerdict.DENY:
                    return {"success": False, "error": f"系统目录禁止作为工作目录: {cwd_raw}"}
                if verdict == PathVerdict.NEED_GRANT:
                    return {
                        "success": False,
                        "error": f"该目录未授权，请先获得用户许可: {cwd_raw}",
                        "action": "need_grant", "path": cwd_raw,
                    }
                cwd = str(policy.safe_resolve(cwd_raw))
            else:
                cwd = str(policy.workspace)    # 默认在 workspace 执行
        else:
            cwd = cwd_raw or "."

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

        if not api_key:
            return {"items": [], "note": "SERPER_API_KEY 未配置，返回空结果"}

        payload: dict[str, Any] = {"q": q, "gl": "cn", "hl": "zh-cn", "page": page}
        if tbs:
            payload["tbs"] = f"qdr:{tbs}"

        headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=config.get("tools.serper_search.timeout", 15)) as client:
            resp = await client.post("https://google.serper.dev/search", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        organic = data.get("organic", [])[: config.get("tools.serper_search.max_results", 10)]
        return {
            "query": q,
            "items": [
                {
                    "title": item.get("title"),
                    "link": item.get("link"),
                    "snippet": item.get("snippet"),
                }
                for item in organic
            ],
        }


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
        from agentos.platform.security.path_policy import PathPolicy, PathVerdict

        policy: PathPolicy | None = kwargs.pop("_path_policy", None)
        raw_path = str(kwargs["file_path"])

        if policy:
            verdict = policy.check_read(raw_path)
            if verdict == PathVerdict.DENY:
                return {"success": False, "error": f"系统目录禁止读取: {raw_path}"}
            if verdict == PathVerdict.NEED_GRANT:
                return {
                    "success": False,
                    "error": f"该目录未授权，请先获得用户许可: {raw_path}",
                    "action": "need_grant", "path": raw_path,
                }
            file_path = policy.safe_resolve(raw_path)
        else:
            file_path = Path(raw_path)

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
        from agentos.platform.security.path_policy import PathPolicy, PathVerdict

        policy: PathPolicy | None = kwargs.pop("_path_policy", None)
        raw_path = str(kwargs["file_path"])

        if policy:
            verdict = policy.check_write(raw_path)
            if verdict == PathVerdict.DENY:
                return {"success": False, "error": f"系统目录禁止写入: {raw_path}"}
            if verdict == PathVerdict.NEED_GRANT:
                return {
                    "success": False,
                    "error": f"该目录未授权，请先获得用户许可: {raw_path}",
                    "action": "need_grant", "path": raw_path,
                }
            file_path = policy.safe_resolve(raw_path)
        else:
            file_path = Path(raw_path)

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


class GrantPathTool(Tool):
    """授权工具。risk_level=HIGH → 自动触发 _needs_confirmation。"""

    name = "grant_path"
    description = "授权 Agent 访问指定目录（需先征得用户同意）"
    risk_level = ToolRiskLevel.HIGH
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "要授权的目录路径"},
        },
        "required": ["path"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        from agentos.platform.security.path_policy import PathPolicy
        policy: PathPolicy | None = kwargs.pop("_path_policy", None)
        path_str = str(kwargs["path"])
        if not policy:
            return {"success": False, "error": "PathPolicy 未初始化"}
        try:
            resolved = policy.grant(path_str)
            return {"success": True, "granted": str(resolved)}
        except ValueError as e:
            return {"success": False, "error": str(e)}


class ImageSearchTool(Tool):
    name = "image_search"
    description = "搜索图片，返回候选图片列表（使用 Serper Images API）"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "图片搜索关键词，使用简短的主题词"}
        },
        "required": ["query"]
    }

    async def execute(self, **kwargs: Any) -> Any:
        from urllib.parse import urlparse

        query = str(kwargs.get("query", "")).strip()
        if not query:
            return {"success": False, "error": "query 不能为空"}

        api_key = config.get("tools.image_search.api_key") or config.get("tools.serper_search.api_key", "")
        if not api_key:
            return {"success": False, "error": "SERPER_API_KEY 未配置"}

        top_k = config.get("tools.image_search.top_k", 10)
        timeout = config.get("tools.image_search.timeout", 30)

        # 构建请求 payload
        payload: dict[str, Any] = {"q": query}
        if any("\u4E00" <= char <= "\u9FFF" for char in query):
            payload.update({"gl": "cn", "hl": "zh-cn"})
        else:
            payload.update({"gl": "us", "hl": "en"})

        headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post("https://google.serper.dev/images", headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()

            raw_items = data.get("images", [])
            results = []
            for item in raw_items[:top_k]:
                if not isinstance(item, dict):
                    continue
                image_url = item.get("imageUrl") or item.get("image_url") or item.get("original")
                if not image_url:
                    continue
                source_page = item.get("link") or item.get("sourceUrl") or ""
                domain = urlparse(source_page).netloc if source_page else ""
                results.append({
                    "title": item.get("title", ""),
                    "image_url": image_url,
                    "source_page": source_page,
                    "source_domain": domain,
                    "thumbnail_url": item.get("thumbnailUrl", ""),
                    "width": item.get("imageWidth"),
                    "height": item.get("imageHeight")
                })

            return {"success": True, "query": query, "top_k": top_k, "results": results}
        except Exception as e:
            return {"success": False, "error": f"图片搜索失败: {str(e)}"}


class DocSourceTool(Tool):
    """文档来源工具，自动识别并获取文档内容"""

    name = "doc_source_tool"
    description = "获取文档内容，自动识别来源（本地文件、飞书、Notion等）"
    risk_level = ToolRiskLevel.LOW
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "文档路径或链接"},
        },
        "required": ["url"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        from agentos.adapters.doc_sources import DocSourceRegistry

        url = str(kwargs["url"])
        adapter = DocSourceRegistry.get_adapter(url)

        if not adapter:
            return {"success": False, "error": f"不支持的文档来源: {url}"}

        try:
            content = adapter.fetch(url)
            return {
                "success": True,
                "content": content,
                "source": adapter.__class__.__name__,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
