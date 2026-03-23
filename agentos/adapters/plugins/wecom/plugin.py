"""企业微信插件入口。"""

from __future__ import annotations

import logging

from agentos.adapters.plugins.base import PluginApi, PluginDefinition, format_missing_dependency_error

logger = logging.getLogger(__name__)

definition = PluginDefinition(
    id="wecom",
    name="企业微信",
    version="0.1.0",
    description="企业微信消息 Channel 插件",
)


async def register(api: PluginApi) -> None:
    """注册企业微信 Channel 和通用 MessageTool。"""
    try:
        from agentos.adapters.plugins.wecom.channel import WecomChannel
        from agentos.adapters.plugins.wecom.config import WecomConfig
    except ImportError as exc:
        error = format_missing_dependency_error(exc)
        api.report_status("failed", error=error)
        logger.info("企业微信插件跳过：%s", error)
        return
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
