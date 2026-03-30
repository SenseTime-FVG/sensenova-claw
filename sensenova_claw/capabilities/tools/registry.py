from __future__ import annotations

from sensenova_claw.capabilities.tools.ask_user_tool import AskUserTool
from sensenova_claw.capabilities.tools.apply_patch_tool import ApplyPatchTool
from sensenova_claw.capabilities.tools.base import Tool
from sensenova_claw.capabilities.tools.builtin import (
    BaiduSearchTool,
    BashCommandTool,
    BraveSearchTool,
    FetchUrlTool,
    ImageSearchTool,
    ManageTodolistTool,
    ReadFileTool,
    SerperSearchTool,
    TavilySearchTool,
    WriteFileTool,
)
from sensenova_claw.capabilities.tools.edit_tool import EditTool
from sensenova_claw.capabilities.tools.email import (
    DownloadAttachmentTool,
    ListEmailsTool,
    MarkEmailTool,
    ReadEmailTool,
    SearchEmailsTool,
    SendEmailTool,
)
from sensenova_claw.capabilities.tools.obsidian_tool import (
    ObsidianIndexTool,
    ObsidianListVaultsTool,
    ObsidianReadTool,
    ObsidianSearchTool,
    ObsidianWriteTool,
)
from sensenova_claw.capabilities.tools.orchestration import CreateAgentTool
from sensenova_claw.capabilities.tools.secret_tools import GetSecretTool, WriteSecretTool
from sensenova_claw.platform.config.config import config


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._register_builtin()

    def _register_builtin(self) -> None:
        for tool in [
            BashCommandTool(),
            SerperSearchTool(),
            ImageSearchTool(),
            BraveSearchTool(),
            BaiduSearchTool(),
            TavilySearchTool(),
            FetchUrlTool(),
            ReadFileTool(),
            WriteFileTool(),
            # secret tool
            GetSecretTool(),
            WriteSecretTool(),

            ManageTodolistTool(),
            ApplyPatchTool(),
            EditTool(),
            CreateAgentTool(),
            AskUserTool(),
        ]:
            self.register(tool)
        # Obsidian 工具：仅在 tools.obsidian.enabled=true 时注册
        if config.get("tools.obsidian.enabled", False):
            for tool in [
                ObsidianSearchTool(),
                ObsidianReadTool(),
                ObsidianWriteTool(),
                ObsidianListVaultsTool(),
                ObsidianIndexTool(),
            ]:
                self.register(tool)
        if config.get("tools.email.enabled", False):
            for tool in [
                SendEmailTool(),
                ListEmailsTool(),
                ReadEmailTool(),
                DownloadAttachmentTool(),
                MarkEmailTool(),
                SearchEmailsTool(),
            ]:
                self.register(tool)

    def register(self, tool: Tool) -> None:
        # 注册工具到内存字典，供 ToolRuntime 查找。
        # 外部依赖：无（仅操作本地数据结构）。
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def _is_llm_exposed(self, tool: Tool) -> bool:
        provider_name, _model_id = config.resolve_model(config.get("llm.default_model"))
        if provider_name == "mock":
            return True
        if tool.name in {"serper_search", "brave_search", "baidu_search", "tavily_search"}:
            return bool(config.get(f"tools.{tool.name}.api_key", ""))
        if tool.name == "image_search":
            return bool(config.get("tools.image_search.api_key", "") or config.get("tools.serper_search.api_key", ""))
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
