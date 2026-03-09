from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from app.core.config import config
from app.tools.base import Tool


class BashCommandTool(Tool):
    name = "bash_command"
    description = "执行 shell 命令"
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
        max_chars = int(config.get("tools.fetch_url.max_size_mb", 5) * 1024 * 1024)
        if len(text) > max_chars:
            text = text[:max_chars]
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
    description = "写入文本文件"
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "content": {"type": "string"},
            "mode": {"type": "string", "enum": ["write", "append"], "default": "write"},
        },
        "required": ["file_path", "content"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        file_path = Path(str(kwargs["file_path"]))
        file_path.parent.mkdir(parents=True, exist_ok=True)
        content = str(kwargs.get("content", ""))
        mode = str(kwargs.get("mode", "write"))
        if mode == "append":
            file_path.open("a", encoding="utf-8").write(content)
        else:
            file_path.write_text(content, encoding="utf-8")
        return {"success": True, "file_path": str(file_path), "size": len(content)}


class SearchSkillTool(Tool):
    name = "search_skill"
    description = "搜索可用 skill"
    parameters = {
        "type": "object",
        "properties": {
            "keyword": {"type": "string"},
        },
    }

    async def execute(self, **kwargs: Any) -> Any:
        keyword = str(kwargs.get("keyword", "")).lower()
        skills = [
            {"skill_name": "skill-creator", "description": "创建技能"},
            {"skill_name": "skill-installer", "description": "安装技能"},
        ]
        if not keyword:
            return skills
        return [s for s in skills if keyword in s["skill_name"].lower() or keyword in s["description"].lower()]


class LoadSkillTool(Tool):
    name = "load_skill"
    description = "加载并执行 skill（v0.1 先返回占位结果）"
    parameters = {
        "type": "object",
        "properties": {
            "skill_name": {"type": "string"},
            "skill_args": {"type": "object"},
        },
        "required": ["skill_name"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        return {
            "success": True,
            "message": "v0.1 未接入真实技能执行引擎",
            "skill_name": kwargs.get("skill_name"),
            "skill_args": kwargs.get("skill_args", {}),
        }
