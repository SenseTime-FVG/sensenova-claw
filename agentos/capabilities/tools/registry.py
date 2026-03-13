from __future__ import annotations

from agentos.capabilities.tools.base import Tool
from agentos.capabilities.tools.builtin import (
    BashCommandTool,
    FetchUrlTool,
    ReadFileTool,
    SerperSearchTool,
    WriteFileTool,
)
from agentos.capabilities.tools.orchestration import CreateAgentTool, CreateWorkflowTool


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._register_builtin()

    def _register_builtin(self) -> None:
        for tool in [
            BashCommandTool(),
            SerperSearchTool(),
            FetchUrlTool(),
            ReadFileTool(),
            WriteFileTool(),
            CreateAgentTool(),
            CreateWorkflowTool(),
        ]:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        # 注册工具到内存字典，供 ToolRuntime 查找。
        # 外部依赖：无（仅操作本地数据结构）。
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def as_llm_tools(self) -> list[dict]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in self._tools.values()
        ]
