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
from sensenova_claw.capabilities.tools.obsidian_locate import ObsidianLocateTool
from sensenova_claw.capabilities.tools.obsidian_tool import (
    ObsidianIndexTool,
    ObsidianListVaultsTool,
    ObsidianReadTool,
    ObsidianSearchTool,
    ObsidianWriteTool,
)
from sensenova_claw.capabilities.tools.citation_tool import PrepareReportCitationsTool
from sensenova_claw.capabilities.tools.orchestration import CreateAgentTool
from sensenova_claw.capabilities.tools.secret_tools import GetSecretTool, WriteSecretTool
from sensenova_claw.capabilities.mcp.runtime import McpSessionManager, McpToolAdapter
from sensenova_claw.platform.config.config import config


# 工具名 → config.yml 中 enabled 字段的映射
# 同一分组的工具共享一个 enabled 开关
_TOOL_CONFIG_KEY_MAP: dict[str, str] = {
    "read_file": "tools.file_operations.enabled",
    "write_file": "tools.file_operations.enabled",
    "edit": "tools.file_operations.enabled",
    "apply_patch": "tools.file_operations.enabled",
}


def _is_tool_config_enabled(tool_name: str) -> bool:
    """根据 config.yml 中 tools.<name>.enabled 判断工具是否启用。

    优先查询 _TOOL_CONFIG_KEY_MAP 中的映射（支持分组开关），
    未映射的工具按 tools.<name>.enabled 查找，默认启用。
    """
    config_key = _TOOL_CONFIG_KEY_MAP.get(tool_name, f"tools.{tool_name}.enabled")
    return bool(config.get(config_key, True))


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._mcp_manager = McpSessionManager()
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
            PrepareReportCitationsTool(),
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
                ObsidianLocateTool(),
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

    def get(self, name: str, *, session_id: str | None = None) -> Tool | None:
        tool = self._tools.get(name)
        if tool is not None or not session_id:
            return tool
        descriptor = None
        for item in self._mcp_manager.get_cached_tools(session_id):
            if item.safe_name == name:
                descriptor = item
                break
        return McpToolAdapter(self._mcp_manager, descriptor) if descriptor else None

    async def ensure_mcp_session(self, session_id: str) -> None:
        await self._mcp_manager.ensure_session(session_id)

    async def dispose_mcp_session(self, session_id: str) -> None:
        await self._mcp_manager.close_session(session_id)

    def _is_llm_exposed(self, tool: Tool) -> bool:
        # 全局 enabled 开关检查（来自 config.yml）
        if not _is_tool_config_enabled(tool.name):
            return False
        provider_name, _model_id = config.resolve_model(config.get("llm.default_model"))
        if provider_name == "mock":
            return True
        if tool.name in {"serper_search", "brave_search", "baidu_search", "tavily_search"}:
            return bool(config.get(f"tools.{tool.name}.api_key", ""))
        if tool.name == "image_search":
            return bool(config.get("tools.image_search.api_key", "") or config.get("tools.serper_search.api_key", ""))
        return True

    def as_llm_tools(self, *, session_id: str | None = None, agent_config: object | None = None) -> list[dict]:
        tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in self._tools.values()
            if self._is_llm_exposed(tool)
        ]
        if session_id:
            for descriptor in self._mcp_manager.get_cached_tools(session_id, agent_config=agent_config):  # type: ignore[arg-type]
                tools.append(
                    {
                        "name": descriptor.safe_name,
                        "description": descriptor.description,
                        "parameters": descriptor.input_schema,
                    }
                )
        tools.sort(key=lambda item: item["name"])
        return tools
