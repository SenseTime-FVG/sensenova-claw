"""Discord 插件入口单元测试。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from sensenova_claw.adapters.plugins import PluginRegistry, _iter_builtin_plugin_modules
from sensenova_claw.adapters.plugins.base import PluginApi
from sensenova_claw.adapters.plugins.discord.plugin import definition, register
from sensenova_claw.interfaces.ws.gateway import Gateway
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.runtime.publisher import EventPublisher


def _make_plugin_api(config_overrides: dict | None = None) -> PluginApi:
    from sensenova_claw.platform.config.config import config as global_config

    defaults = {
        "enabled": False,
        "bot_token": "discord-token",
        "dm_policy": "open",
        "group_policy": "allowlist",
        "allowlist": [],
        "group_allowlist": [],
        "channel_allowlist": [],
        "require_mention": True,
        "show_tool_progress": False,
        "reply_in_thread": True,
    }
    if config_overrides:
        defaults.update(config_overrides)

    for key, value in defaults.items():
        global_config.set(f"plugins.discord.{key}", value)

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)
    registry = PluginRegistry()
    registry._gateway = gateway
    registry._publisher = publisher
    return PluginApi(plugin_id="discord", registry=registry)


class TestPluginDefinition:
    def test_id(self):
        assert definition.id == "discord"

    def test_name(self):
        assert definition.name == "Discord"

    def test_description_not_empty(self):
        assert len(definition.description) > 0


class TestRegister:
    @pytest.mark.asyncio
    async def test_disabled_does_nothing(self):
        api = _make_plugin_api({"enabled": False})
        registry = api._registry
        await register(api)
        assert registry._pending_channels == []
        assert registry._pending_tools == []

    @pytest.mark.asyncio
    async def test_enabled_but_missing_dependency_skips_plugin(self):
        api = _make_plugin_api({"enabled": True})
        registry = api._registry
        with patch("sensenova_claw.adapters.plugins.discord.plugin.importlib.util.find_spec", return_value=None):
            await register(api)
        assert registry._pending_channels == []
        assert registry._pending_tools == []

    @pytest.mark.asyncio
    async def test_enabled_registers_channel_and_message_tool(self):
        api = _make_plugin_api({"enabled": True})
        registry = api._registry
        with patch("sensenova_claw.adapters.plugins.discord.plugin.importlib.util.find_spec", return_value=object()):
            await register(api)
        assert len(registry._pending_channels) == 1
        assert registry._pending_channels[0].get_channel_id() == "discord"
        assert len(registry._pending_tools) == 1

    @pytest.mark.asyncio
    async def test_channel_config_passthrough(self):
        api = _make_plugin_api(
            {
                "enabled": True,
                "group_policy": "open",
                "channel_allowlist": ["thread-1"],
                "reply_in_thread": False,
            }
        )
        registry = api._registry
        with patch("sensenova_claw.adapters.plugins.discord.plugin.importlib.util.find_spec", return_value=object()):
            await register(api)
        channel = registry._pending_channels[0]
        assert channel._config.group_policy == "open"
        assert channel._config.channel_allowlist == ["thread-1"]
        assert channel._config.reply_in_thread is False


@pytest.mark.asyncio
async def test_plugin_registry_loads_discord_plugin():
    from sensenova_claw.platform.config.config import config as global_config

    global_config.set("plugins.feishu.enabled", False)
    global_config.set("plugins.wecom.enabled", False)
    global_config.set("plugins.telegram.enabled", False)
    global_config.set("plugins.whatsapp.enabled", False)
    global_config.set("plugins.discord.enabled", False)

    registry = PluginRegistry()
    await registry.load_plugins(config=global_config.data)

    assert "discord" in registry._plugins


def test_builtin_plugin_module_points_to_plugins_package():
    modules = dict(_iter_builtin_plugin_modules())
    assert modules["discord"] == "sensenova_claw.adapters.plugins.discord.plugin"
