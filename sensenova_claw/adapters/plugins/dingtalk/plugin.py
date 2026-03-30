"""DingTalk 插件入口。"""

from __future__ import annotations

import importlib
import logging

from sensenova_claw.adapters.plugins.base import PluginApi, PluginDefinition, format_missing_dependency_error

logger = logging.getLogger(__name__)

definition = PluginDefinition(
    id="dingtalk",
    name="DingTalk",
    version="0.1.0",
    description="DingTalk Stream Channel 插件（基于官方 dingtalk-stream-sdk-python）",
)


async def register(api: PluginApi) -> None:
    """注册 DingTalk Channel 和通用 MessageTool。"""
    from sensenova_claw.adapters.plugins.dingtalk.config import DingtalkConfig

    cfg = DingtalkConfig.from_plugin_api(api)
    if not cfg.enabled:
        return

    try:
        importlib.import_module("dingtalk_stream")
        from sensenova_claw.adapters.plugins.dingtalk.channel import DingtalkChannel
    except ImportError as exc:
        error = format_missing_dependency_error(exc, package_hint="dingtalk_stream")
        api.report_status("failed", error=error)
        logger.info("DingTalk 插件跳过：%s（pip install dingtalk-stream）", error)
        return

    from sensenova_claw.capabilities.tools.message_tool import MessageTool

    channel = DingtalkChannel(config=cfg, plugin_api=api)
    api.register_channel(channel)
    api.register_tool(
        MessageTool(
            gateway=api.get_gateway(),
            publisher=api.get_publisher(),
        )
    )
