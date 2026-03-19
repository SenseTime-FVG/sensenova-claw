"""WhatsApp 插件入口。"""

from __future__ import annotations

import logging

from agentos.adapters.plugins.base import PluginApi, PluginDefinition

logger = logging.getLogger(__name__)

definition = PluginDefinition(
    id="whatsapp",
    name="WhatsApp",
    version="0.1.0",
    description="WhatsApp Web 核心 Channel 插件",
)


async def register(api: PluginApi) -> None:
    """注册 WhatsApp Channel 和通用 MessageTool。"""
    try:
        from agentos.adapters.plugins.whatsapp.channel import WhatsAppChannel
        from agentos.adapters.plugins.whatsapp.config import WhatsAppConfig
    except ImportError:
        logger.info("WhatsApp 插件跳过：缺少依赖")
        return

    from agentos.capabilities.tools.message_tool import MessageTool

    cfg = WhatsAppConfig.from_plugin_api(api)
    if not cfg.enabled:
        return

    channel = WhatsAppChannel(config=cfg, plugin_api=api)
    api.register_channel(channel)
    api.register_tool(
        MessageTool(
            gateway=api.get_gateway(),
            publisher=api.get_publisher(),
        )
    )
