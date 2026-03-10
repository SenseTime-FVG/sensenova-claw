from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from app.core.config import config
from app.tools.base import Tool, ToolRiskLevel


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
        command = str(kwargs.get("command", ""))
        cwd = kwargs.get("working_dir") or "."
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        return {
            "return_code": proc.returncode,
            "stdout": out.decode("utf-8", errors="replace"),
            "stderr": err.decode("utf-8", errors="replace"),
        }


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
        file_path = Path(str(kwargs["file_path"]))
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
        file_path = Path(str(kwargs["file_path"]))
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


