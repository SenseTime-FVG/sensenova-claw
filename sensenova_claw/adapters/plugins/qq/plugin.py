"""QQ 插件入口。"""

from __future__ import annotations

import logging

from sensenova_claw.adapters.plugins.base import PluginApi, PluginDefinition, format_missing_dependency_error

logger = logging.getLogger(__name__)

definition = PluginDefinition(
    id="qq",
    name="QQ",
    version="0.1.0",
    description="QQ Channel 插件，统一支持官方开放平台与 OneBot/NapCat。",
)


async def register(api: PluginApi) -> None:
    """注册 QQ Channel 和通用 MessageTool。"""
    try:
        from sensenova_claw.adapters.plugins.qq.channel import QQChannel
        from sensenova_claw.adapters.plugins.qq.config import QQConfig
    except ImportError as exc:
        error = format_missing_dependency_error(exc, package_hint="websockets")
        api.report_status("failed", error=error)
        logger.info("QQ 插件跳过：%s", error)
        return

    from sensenova_claw.capabilities.tools.message_tool import MessageTool

    cfg = QQConfig.from_plugin_api(api)
    if not cfg.enabled:
        return

    channel = QQChannel(config=cfg, plugin_api=api)
    api.register_channel(channel)
    api.register_tool(
        MessageTool(
            gateway=api.get_gateway(),
            publisher=api.get_publisher(),
        )
    )
