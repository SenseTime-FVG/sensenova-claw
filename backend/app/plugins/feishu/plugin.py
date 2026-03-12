"""飞书插件入口：暴露 definition 和 register 函数"""

from __future__ import annotations

from app.plugins.base import PluginApi, PluginDefinition

definition = PluginDefinition(
    id="feishu",
    name="飞书",
    version="0.9.0",
    description="飞书/Lark 消息 Channel 插件（含 Markdown 卡片、主动出站、API 调用）",
)


async def register(api: PluginApi) -> None:
    """注册飞书 Channel + MessageTool + FeishuApiTool 到框架"""
    from .channel import FeishuChannel
    from .config import FeishuConfig

    feishu_config = FeishuConfig.from_plugin_api(api)
    if not feishu_config.enabled:
        return

    channel = FeishuChannel(config=feishu_config, plugin_api=api)
    api.register_channel(channel)

    # 注册 MessageTool（主动发消息）
    from app.tools.message_tool import MessageTool
    api.register_tool(MessageTool(
        gateway=api.get_gateway(),
        publisher=api.get_publisher(),
    ))

    # 按配置注册 FeishuApiTool（懒引用 channel._client，start() 后可用）
    api_tool_config = api.get_config("api_tool", {})
    if api_tool_config.get("enabled", False):
        from app.tools.feishu_api_tool import FeishuApiTool
        api.register_tool(FeishuApiTool(
            feishu_channel=channel,
            allowed_methods=api_tool_config.get("allowed_methods", ["GET"]),
            allowed_path_prefixes=api_tool_config.get("allowed_path_prefixes", []),
        ))
