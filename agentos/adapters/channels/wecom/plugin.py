"""企业微信插件入口。"""

from __future__ import annotations

from agentos.adapters.plugins.base import PluginApi, PluginDefinition

definition = PluginDefinition(
    id="wecom",
    name="企业微信",
    version="0.1.0",
    description="企业微信消息 Channel 插件",
)


async def register(api: PluginApi) -> None:
    """注册企业微信 Channel 和通用 MessageTool。"""
    from agentos.adapters.channels.wecom.channel import WecomChannel
    from agentos.adapters.channels.wecom.config import WecomConfig
    from agentos.capabilities.tools.message_tool import MessageTool

    cfg = WecomConfig.from_plugin_api(api)
    if not cfg.enabled:
        return

    channel = WecomChannel(config=cfg, plugin_api=api)
    api.register_channel(channel)
    api.register_tool(
        MessageTool(
            gateway=api.get_gateway(),
            publisher=api.get_publisher(),
        )
    )
