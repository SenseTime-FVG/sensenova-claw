"""Discord 插件入口。"""

from __future__ import annotations

import importlib.util
import logging

from agentos.adapters.plugins.base import PluginApi, PluginDefinition

logger = logging.getLogger(__name__)

definition = PluginDefinition(
    id="discord",
    name="Discord",
    version="0.1.0",
    description="Discord Bot Channel 插件（支持 DM、群聊 mention 和线程路由）",
)


async def register(api: PluginApi) -> None:
    """注册 Discord Channel 和通用 MessageTool。"""
    from agentos.adapters.plugins.discord.config import DiscordConfig

    cfg = DiscordConfig.from_plugin_api(api)
    if not cfg.enabled:
        return

    if importlib.util.find_spec("discord") is None:
        error = "未安装依赖: discord.py"
        api.report_status("failed", error=error)
        logger.info("Discord 插件跳过：%s（pip install discord.py）", error)
        return

    from agentos.adapters.plugins.discord.channel import DiscordChannel
    from agentos.capabilities.tools.message_tool import MessageTool

    channel = DiscordChannel(config=cfg, plugin_api=api)
    api.register_channel(channel)
    api.register_tool(
        MessageTool(
            gateway=api.get_gateway(),
            publisher=api.get_publisher(),
        )
    )
