"""企微插件入口 plugin.py 单元测试"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from sensenova_claw.adapters.plugins import PluginRegistry, _iter_builtin_plugin_modules
from sensenova_claw.adapters.plugins.wecom.plugin import definition, register
from sensenova_claw.adapters.plugins.base import PluginApi
from sensenova_claw.interfaces.ws.gateway import Gateway
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.runtime.publisher import EventPublisher


def _make_plugin_api(config_overrides: dict | None = None) -> PluginApi:
    from sensenova_claw.platform.config.config import config as global_config

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

    async def test_missing_dependency_reports_failed_state(self):
        api = _make_plugin_api({"enabled": True})
        registry = api._registry
        original_import = __import__
        with patch(
            "builtins.__import__",
            side_effect=lambda name, *args, **kwargs: (
                (_ for _ in ()).throw(ModuleNotFoundError(name="pyee"))
                if name == "sensenova_claw.adapters.plugins.wecom.channel"
                else original_import(name, *args, **kwargs)
            ),
        ):
            await register(api)
        assert registry._pending_channels == []
        assert registry._plugin_states["wecom"]["status"] == "failed"
        assert registry._plugin_states["wecom"]["error"] == "未安装依赖: pyee"

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
    from sensenova_claw.platform.config.config import config as global_config

    global_config.set("plugins.feishu.enabled", False)
    global_config.set("plugins.wecom.enabled", False)
    global_config.set("plugins.telegram.enabled", False)
    global_config.set("plugins.whatsapp.enabled", False)
    global_config.set("plugins.discord.enabled", False)

    registry = PluginRegistry()
    await registry.load_plugins(config=global_config.data)

    assert "feishu" in registry._plugins
    assert "wecom" in registry._plugins
    assert "telegram" in registry._plugins
    assert "whatsapp" in registry._plugins
    assert "discord" in registry._plugins


def test_builtin_plugin_module_points_to_plugins_package():
    modules = dict(_iter_builtin_plugin_modules())
    assert modules["wecom"] == "sensenova_claw.adapters.plugins.wecom.plugin"
    assert modules["discord"] == "sensenova_claw.adapters.plugins.discord.plugin"
