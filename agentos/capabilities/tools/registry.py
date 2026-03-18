from __future__ import annotations

from agentos.capabilities.tools.base import Tool
from agentos.capabilities.tools.builtin import (
    BaiduSearchTool,
    BashCommandTool,
    BraveSearchTool,
    FetchUrlTool,
    ReadFileTool,
    SerperSearchTool,
    TavilySearchTool,
    WriteFileTool,
)
from agentos.capabilities.tools.orchestration import CreateAgentTool
from agentos.platform.config.config import config


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._register_builtin()

    def _register_builtin(self) -> None:
        for tool in [
            BashCommandTool(),
            SerperSearchTool(),
            BraveSearchTool(),
            BaiduSearchTool(),
            TavilySearchTool(),
            FetchUrlTool(),
            ReadFileTool(),
            WriteFileTool(),
            CreateAgentTool(),
        ]:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        # 注册工具到内存字典，供 ToolRuntime 查找。
        # 外部依赖：无（仅操作本地数据结构）。
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def _is_llm_exposed(self, tool: Tool) -> bool:
        if config.get("agent.provider") == "mock":
            return True
        if tool.name in {"serper_search", "brave_search", "baidu_search", "tavily_search"}:
            return bool(config.get(f"tools.{tool.name}.api_key", ""))
        return True

    def as_llm_tools(self) -> list[dict]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in self._tools.values()
            if self._is_llm_exposed(tool)
        ]
