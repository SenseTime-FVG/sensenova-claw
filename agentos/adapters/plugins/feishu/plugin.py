"""飞书插件入口：暴露 definition 和 register 函数"""

from __future__ import annotations

from agentos.adapters.plugins.base import PluginApi, PluginDefinition

definition = PluginDefinition(
    id="feishu",
    name="飞书",
    version="0.9.0",
    description="飞书/Lark 消息 Channel 插件（含 Markdown 卡片与主动出站）",
)


async def register(api: PluginApi) -> None:
    """注册飞书 Channel + MessageTool 到框架"""
    from .channel import FeishuChannel
    from .config import FeishuConfig

    feishu_config = FeishuConfig.from_plugin_api(api)
    if not feishu_config.enabled:
        return

    channel = FeishuChannel(config=feishu_config, plugin_api=api)
    api.register_channel(channel)

    # 注册 MessageTool（主动发消息）
    from agentos.capabilities.tools.message_tool import MessageTool
    api.register_tool(MessageTool(
        gateway=api.get_gateway(),
        publisher=api.get_publisher(),
    ))

    # 读取工具配置
    tools_config = api.get_config("tools", {})

    # 注册专用工具（默认启用）
    if tools_config.get("doc", True):
        from agentos.capabilities.tools.feishu_doc_tool import FeishuDocTool
        api.register_tool(FeishuDocTool(feishu_channel=channel))

    if tools_config.get("wiki", True):
        from agentos.capabilities.tools.feishu_wiki_tool import FeishuWikiTool
        api.register_tool(FeishuWikiTool(feishu_channel=channel))

    if tools_config.get("drive", True):
        from agentos.capabilities.tools.feishu_drive_tool import FeishuDriveTool
        api.register_tool(FeishuDriveTool(feishu_channel=channel))

    if tools_config.get("perm", False):  # 默认禁用
        from agentos.capabilities.tools.feishu_perm_tool import FeishuPermTool
        api.register_tool(FeishuPermTool(feishu_channel=channel))
