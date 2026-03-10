"""飞书插件入口：暴露 definition 和 register 函数"""

from __future__ import annotations

from app.plugins.base import PluginApi, PluginDefinition

definition = PluginDefinition(
    id="feishu",
    name="飞书",
    version="0.1.0",
    description="飞书/Lark 消息 Channel 插件",
)


async def register(api: PluginApi) -> None:
    """注册飞书 Channel 到框架"""
    from .channel import FeishuChannel
    from .config import FeishuConfig

    feishu_config = FeishuConfig.from_plugin_api(api)
    if not feishu_config.enabled:
        return

    channel = FeishuChannel(config=feishu_config, plugin_api=api)
    api.register_channel(channel)
