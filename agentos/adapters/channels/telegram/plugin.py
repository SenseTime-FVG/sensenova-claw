"""Telegram 插件入口。"""

from __future__ import annotations

from agentos.adapters.plugins.base import PluginApi, PluginDefinition

definition = PluginDefinition(
    id="telegram",
    name="Telegram",
    version="0.1.0",
    description="Telegram Bot Channel 插件（基于 python-telegram-bot）",
)


async def register(api: PluginApi) -> None:
    """注册 Telegram Channel 和通用 MessageTool。"""
    from agentos.capabilities.tools.message_tool import MessageTool

    from .channel import TelegramChannel
    from .config import TelegramConfig

    cfg = TelegramConfig.from_plugin_api(api)
    if not cfg.enabled:
        return

    channel = TelegramChannel(config=cfg, plugin_api=api)
    api.register_channel(channel)
    api.register_tool(
        MessageTool(
            gateway=api.get_gateway(),
            publisher=api.get_publisher(),
        )
    )
