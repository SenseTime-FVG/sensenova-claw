"""记忆搜索工具：memory_search"""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

from agentos.capabilities.tools.base import Tool

if TYPE_CHECKING:
    from agentos.capabilities.memory.manager import MemoryManager


class MemorySearchTool(Tool):
    name = "memory_search"
    description = "搜索长期记忆文件（MEMORY.md + memory/*.md），返回与查询最相关的片段"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询"},
            "max_results": {"type": "integer", "description": "最大返回数，默认5"},
        },
        "required": ["query"],
    }

    def __init__(self, memory_manager: MemoryManager):
        self._manager = memory_manager

    async def execute(self, **kwargs: Any) -> Any:
        query = kwargs.get("query", "")
        max_results = int(kwargs.get("max_results", 5))

        if not query:
            return json.dumps({"error": "query 不能为空"}, ensure_ascii=False)

        results = await self._manager.search(query, max_results=max_results)

        if not results:
            return json.dumps({"results": [], "message": "未找到相关记忆"}, ensure_ascii=False)

        return json.dumps(
            {
                "results": [
                    {
                        "snippet": r.snippet,
                        "path": r.path,
                        "start_line": r.start_line,
                        "end_line": r.end_line,
                        "score": round(r.score, 4),
                    }
                    for r in results
                ]
            },
            ensure_ascii=False,
        )
