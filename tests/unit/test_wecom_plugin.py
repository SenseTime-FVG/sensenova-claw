"""企微插件入口 plugin.py 单元测试"""

from __future__ import annotations

import pytest

from agentos.adapters.channels.wecom.plugin import definition, register
from agentos.adapters.plugins import PluginRegistry
from agentos.adapters.plugins.base import PluginApi
from agentos.interfaces.ws.gateway import Gateway
from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.runtime.publisher import EventPublisher


def _make_plugin_api(config_overrides: dict | None = None) -> PluginApi:
    from agentos.platform.config.config import config as global_config

    defaults = {
        "enabled": False,
        "bot_id": "bot_001",
        "secret": "secret_001",
        "websocket_url": "wss://openws.work.weixin.qq.com",
        "dm_policy": "open",
        "group_policy": "open",
        "allowlist": [],
        "group_allowlist": [],
        "show_tool_progress": False,
    }
    if config_overrides:
        defaults.update(config_overrides)

    for key, value in defaults.items():
        global_config.set(f"plugins.wecom.{key}", value)

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    registry = PluginRegistry()
    registry._gateway = gateway
    registry._publisher = publisher
    return PluginApi(plugin_id="wecom", registry=registry)


class TestPluginDefinition:
    def test_id(self):
        assert definition.id == "wecom"

    def test_name(self):
        assert definition.name == "企业微信"

    def test_description_not_empty(self):
        assert len(definition.description) > 0


class TestRegister:
    async def test_disabled_does_nothing(self):
        api = _make_plugin_api({"enabled": False})
        registry = api._registry
        await register(api)
        assert len(registry._pending_channels) == 0
        assert len(registry._pending_tools) == 0

    async def test_enabled_registers_channel_and_message_tool(self):
        api = _make_plugin_api({"enabled": True})
        registry = api._registry
        await register(api)
        assert len(registry._pending_channels) == 1
        assert registry._pending_channels[0].get_channel_id() == "wecom"
        assert len(registry._pending_tools) == 1

    async def test_channel_config_passthrough(self):
        api = _make_plugin_api({
            "enabled": True,
            "bot_id": "custom_bot",
            "secret": "custom_secret",
            "group_policy": "allowlist",
        })
        registry = api._registry
        await register(api)
        channel = registry._pending_channels[0]
        assert channel._config.bot_id == "custom_bot"
        assert channel._config.secret == "custom_secret"
        assert channel._config.group_policy == "allowlist"


@pytest.mark.asyncio
async def test_plugin_registry_loads_channel_plugins():
    from agentos.platform.config.config import config as global_config

    global_config.set("plugins.feishu.enabled", False)
    global_config.set("plugins.wecom.enabled", False)

    registry = PluginRegistry()
    await registry.load_plugins(config=global_config.data)

    assert "feishu" in registry._plugins
    assert "wecom" in registry._plugins
