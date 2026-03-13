"""飞书插件入口 plugin.py 集成测试

去除所有 mock/MagicMock/AsyncMock/patch，使用真实组件验证：
- PluginDefinition 元信息
- register() 函数：启用/禁用行为、Channel/Tool 注册
"""

from __future__ import annotations

import pytest

from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.runtime.publisher import EventPublisher
from agentos.interfaces.ws.gateway import Gateway
from agentos.adapters.plugins import PluginRegistry
from agentos.adapters.plugins.base import PluginApi
from agentos.adapters.channels.feishu.plugin import definition, register


# ---- 辅助：构造真实 PluginApi ----


def _make_plugin_api(config_overrides: dict | None = None) -> PluginApi:
    """构造真实的 PluginApi，使用真实 PluginRegistry / Gateway / EventPublisher。

    通过直接设置 config 中的 plugins.feishu 字段来控制测试配置。
    """
    from agentos.platform.config.config import config as global_config

    # 备份原始 feishu 配置
    defaults = {
        "enabled": False,
        "app_id": "test_app",
        "app_secret": "test_secret",
        "dm_policy": "open",
        "group_policy": "mention",
        "allowlist": [],
        "log_level": "INFO",
        "render_mode": "card",
        "show_tool_progress": False,
        "api_tool": {},
    }
    if config_overrides:
        defaults.update(config_overrides)

    # 将测试配置写入全局 config
    for key, value in defaults.items():
        global_config.set(f"plugins.feishu.{key}", value)

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    registry = PluginRegistry()
    registry._gateway = gateway
    registry._publisher = publisher

    api = PluginApi(plugin_id="feishu", registry=registry)
    return api


# ---- PluginDefinition 测试 ----


class TestPluginDefinition:
    def test_id(self):
        assert definition.id == "feishu"

    def test_name(self):
        assert definition.name == "飞书"

    def test_version(self):
        assert definition.version == "0.9.0"

    def test_description_not_empty(self):
        assert len(definition.description) > 0


# ---- register() 测试 ----


class TestRegister:
    async def test_disabled_does_nothing(self):
        """enabled=False 时不应注册任何 Channel 或 Tool"""
        api = _make_plugin_api({"enabled": False})
        registry = api._registry
        await register(api)
        assert len(registry._pending_channels) == 0
        assert len(registry._pending_tools) == 0

    async def test_enabled_registers_channel(self):
        """enabled=True 时应注册 FeishuChannel"""
        api = _make_plugin_api({"enabled": True})
        registry = api._registry
        await register(api)
        assert len(registry._pending_channels) == 1
        channel = registry._pending_channels[0]
        assert channel.get_channel_id() == "feishu"

    async def test_enabled_registers_message_tool(self):
        """enabled=True 时应注册 MessageTool"""
        api = _make_plugin_api({"enabled": True})
        registry = api._registry
        await register(api)
        # register_tool 至少被调用一次（MessageTool）
        assert len(registry._pending_tools) >= 1

    async def test_api_tool_disabled_by_default(self):
        """默认不启用 api_tool 时，只注册 MessageTool（1 次）"""
        api = _make_plugin_api({"enabled": True, "api_tool": {}})
        registry = api._registry
        await register(api)
        assert len(registry._pending_tools) == 1  # 仅 MessageTool

    async def test_api_tool_enabled(self):
        """api_tool.enabled=True 时应额外注册 FeishuApiTool"""
        api = _make_plugin_api({
            "enabled": True,
            "api_tool": {
                "enabled": True,
                "allowed_methods": ["GET", "POST"],
                "allowed_path_prefixes": ["/open-apis/im"],
            },
        })
        registry = api._registry
        await register(api)
        # MessageTool + FeishuApiTool = 2
        assert len(registry._pending_tools) == 2

    async def test_channel_config_passthrough(self):
        """Channel 应使用 FeishuConfig 中的配置值"""
        api = _make_plugin_api({
            "enabled": True,
            "app_id": "my_app",
            "app_secret": "my_secret",
            "render_mode": "text",
        })
        registry = api._registry
        await register(api)
        channel = registry._pending_channels[0]
        assert channel._config.app_id == "my_app"
        assert channel._config.app_secret == "my_secret"
        assert channel._config.render_mode == "text"
