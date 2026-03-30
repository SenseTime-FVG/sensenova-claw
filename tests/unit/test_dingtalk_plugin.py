"""DingTalk 插件入口单元测试。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from sensenova_claw.adapters.plugins import PluginRegistry, _iter_builtin_plugin_modules
from sensenova_claw.adapters.plugins.base import PluginApi
from sensenova_claw.adapters.plugins.dingtalk.plugin import definition, register
from sensenova_claw.interfaces.ws.gateway import Gateway
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.runtime.publisher import EventPublisher


def _make_plugin_api(config_overrides: dict | None = None) -> PluginApi:
    from sensenova_claw.platform.config.config import config as global_config

    defaults = {
        "enabled": False,
        "client_id": "ding-app-key",
        "client_secret": "ding-app-secret",
        "dm_policy": "open",
        "group_policy": "open",
        "allowlist": [],
        "group_allowlist": [],
        "require_mention": True,
        "show_tool_progress": False,
        "reply_to_sender": False,
    }
    if config_overrides:
        defaults.update(config_overrides)

    for key, value in defaults.items():
        global_config.set(f"plugins.dingtalk.{key}", value)

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)
    registry = PluginRegistry()
    registry._gateway = gateway
    registry._publisher = publisher
    return PluginApi(plugin_id="dingtalk", registry=registry)


class TestPluginDefinition:
    def test_id(self):
        assert definition.id == "dingtalk"

    def test_name(self):
        assert definition.name == "DingTalk"

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
    async def test_enabled_registers_channel_and_message_tool(self):
        api = _make_plugin_api({"enabled": True})
        registry = api._registry
        with patch("sensenova_claw.adapters.plugins.dingtalk.plugin.importlib.import_module", return_value=object()):
            await register(api)
        assert len(registry._pending_channels) == 1
        assert registry._pending_channels[0].get_channel_id() == "dingtalk"
        assert len(registry._pending_tools) == 1

    @pytest.mark.asyncio
    async def test_missing_dependency_reports_failed_state(self):
        api = _make_plugin_api({"enabled": True})
        registry = api._registry
        original_import = __import__
        with patch(
            "builtins.__import__",
            side_effect=lambda name, *args, **kwargs: (
                (_ for _ in ()).throw(ModuleNotFoundError(name="dingtalk_stream"))
                if name == "sensenova_claw.adapters.plugins.dingtalk.channel"
                else original_import(name, *args, **kwargs)
            ),
        ):
            await register(api)
        assert registry._pending_channels == []
        assert registry._plugin_states["dingtalk"]["status"] == "failed"
        assert registry._plugin_states["dingtalk"]["error"] == "未安装依赖: dingtalk_stream"

    @pytest.mark.asyncio
    async def test_channel_config_passthrough(self):
        api = _make_plugin_api(
            {
                "enabled": True,
                "group_policy": "allowlist",
                "group_allowlist": ["staff-9"],
                "reply_to_sender": True,
            }
        )
        registry = api._registry
        with patch("sensenova_claw.adapters.plugins.dingtalk.plugin.importlib.import_module", return_value=object()):
            await register(api)
        channel = registry._pending_channels[0]
        assert channel._config.group_policy == "allowlist"
        assert channel._config.group_allowlist == ["staff-9"]
        assert channel._config.reply_to_sender is True


@pytest.mark.asyncio
async def test_plugin_registry_loads_dingtalk_plugin():
    from sensenova_claw.platform.config.config import config as global_config

    global_config.set("plugins.feishu.enabled", False)
    global_config.set("plugins.wecom.enabled", False)
    global_config.set("plugins.telegram.enabled", False)
    global_config.set("plugins.whatsapp.enabled", False)
    global_config.set("plugins.discord.enabled", False)
    global_config.set("plugins.dingtalk.enabled", False)

    registry = PluginRegistry()
    await registry.load_plugins(config=global_config.data)

    assert "dingtalk" in registry._plugins


def test_builtin_plugin_module_points_to_plugins_package():
    modules = dict(_iter_builtin_plugin_modules())
    assert modules["dingtalk"] == "sensenova_claw.adapters.plugins.dingtalk.plugin"
