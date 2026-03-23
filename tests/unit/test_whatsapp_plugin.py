"""WhatsApp 插件入口单元测试。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from agentos.adapters.plugins.whatsapp.plugin import definition, register
from agentos.adapters.plugins import PluginRegistry
from agentos.adapters.plugins.base import PluginApi
from agentos.interfaces.ws.gateway import Gateway
from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.runtime.publisher import EventPublisher


def _make_plugin_api(config_overrides: dict | None = None) -> PluginApi:
    from agentos.platform.config.config import config as global_config

    defaults = {
        "enabled": False,
        "auth_dir": "/tmp/agentos-whatsapp-auth",
        "dm_policy": "open",
        "group_policy": "open",
        "allowlist": [],
        "group_allowlist": [],
        "show_tool_progress": False,
        "bridge": {
            "command": "node",
            "entry": "/tmp/bridge/index.mjs",
            "startup_timeout_seconds": 30,
            "send_timeout_seconds": 15,
        },
    }
    if config_overrides:
        defaults.update(config_overrides)

    for key, value in defaults.items():
        global_config.set(f"plugins.whatsapp.{key}", value)

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    registry = PluginRegistry()
    registry._gateway = gateway
    registry._publisher = publisher
    return PluginApi(plugin_id="whatsapp", registry=registry)


class TestPluginDefinition:
    def test_id(self):
        assert definition.id == "whatsapp"

    def test_name(self):
        assert definition.name == "WhatsApp"

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
        await register(api)
        assert len(registry._pending_channels) == 1
        assert registry._pending_channels[0].get_channel_id() == "whatsapp"
        assert len(registry._pending_tools) == 1

    @pytest.mark.asyncio
    async def test_missing_dependency_reports_failed_state(self):
        api = _make_plugin_api({"enabled": True})
        registry = api._registry
        original_import = __import__
        with patch(
            "builtins.__import__",
            side_effect=lambda name, *args, **kwargs: (
                (_ for _ in ()).throw(ModuleNotFoundError(name="pyee"))
                if name == "agentos.adapters.plugins.whatsapp.channel"
                else original_import(name, *args, **kwargs)
            ),
        ):
            await register(api)
        assert registry._pending_channels == []
        assert registry._plugin_states["whatsapp"]["status"] == "failed"
        assert registry._plugin_states["whatsapp"]["error"] == "未安装依赖: pyee"

    @pytest.mark.asyncio
    async def test_channel_config_passthrough(self):
        api = _make_plugin_api(
            {
                "enabled": True,
                "auth_dir": "/tmp/custom-auth",
                "group_policy": "allowlist",
                "group_allowlist": ["group-1@g.us"],
                "bridge": {"command": "node-custom", "entry": "/tmp/custom/index.mjs"},
            }
        )
        registry = api._registry
        await register(api)
        channel = registry._pending_channels[0]
        assert channel._config.auth_dir == str(Path("/tmp/custom-auth").resolve())
        assert channel._config.group_policy == "allowlist"
        assert channel._config.group_allowlist == ["group-1@g.us"]
        assert channel._config.bridge.command == "node-custom"
        assert channel._config.bridge.entry == "/tmp/custom/index.mjs"
