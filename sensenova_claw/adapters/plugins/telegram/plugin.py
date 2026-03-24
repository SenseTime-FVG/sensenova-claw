"""Telegram 插件入口。"""

from __future__ import annotations

import logging

from sensenova_claw.adapters.plugins.base import PluginApi, PluginDefinition, format_missing_dependency_error

logger = logging.getLogger(__name__)

definition = PluginDefinition(
    id="telegram",
    name="Telegram",
    version="0.1.0",
    description="Telegram Bot Channel 插件（基于 python-telegram-bot）",
)


async def register(api: PluginApi) -> None:
    """注册 Telegram Channel 和通用 MessageTool。"""
    try:
        from sensenova_claw.adapters.plugins.telegram.channel import TelegramChannel
        from sensenova_claw.adapters.plugins.telegram.config import TelegramConfig
    except ImportError as exc:
        error = format_missing_dependency_error(exc, package_hint="python-telegram-bot")
        api.report_status("failed", error=error)
        logger.info("Telegram 插件跳过：%s（pip install python-telegram-bot）", error)
        return

    from sensenova_claw.capabilities.tools.message_tool import MessageTool

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
