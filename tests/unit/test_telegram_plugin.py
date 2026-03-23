"""Telegram 插件入口单元测试。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

telegram = pytest.importorskip("telegram", reason="python-telegram-bot not installed")

from agentos.adapters.plugins.telegram.plugin import definition, register
from agentos.adapters.plugins import PluginRegistry
from agentos.adapters.plugins.base import PluginApi
from agentos.interfaces.ws.gateway import Gateway
from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.runtime.publisher import EventPublisher


def _make_plugin_api(config_overrides: dict | None = None) -> PluginApi:
    from agentos.platform.config.config import config as global_config

    defaults = {
        "enabled": False,
        "bot_token": "123:abc",
        "mode": "polling",
        "dm_policy": "open",
        "group_policy": "allowlist",
        "allowlist": [],
        "group_allowlist": [],
        "group_chat_allowlist": [],
        "require_mention": True,
        "show_tool_progress": False,
        "reply_to_message": True,
        "polling_timeout_seconds": 30,
        "webhook_url": "",
        "webhook_secret": "",
        "webhook_path": "/telegram-webhook",
        "webhook_host": "127.0.0.1",
        "webhook_port": 8787,
    }
    if config_overrides:
        defaults.update(config_overrides)

    for key, value in defaults.items():
        global_config.set(f"plugins.telegram.{key}", value)

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)

    registry = PluginRegistry()
    registry._gateway = gateway
    registry._publisher = publisher
    return PluginApi(plugin_id="telegram", registry=registry)


class TestPluginDefinition:
    def test_id(self):
        assert definition.id == "telegram"

    def test_name(self):
        assert definition.name == "Telegram"

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
        assert registry._pending_channels[0].get_channel_id() == "telegram"
        assert len(registry._pending_tools) == 1

    @pytest.mark.asyncio
    async def test_missing_dependency_reports_failed_state(self):
        api = _make_plugin_api({"enabled": True})
        registry = api._registry
        original_import = __import__
        with patch(
            "builtins.__import__",
            side_effect=lambda name, *args, **kwargs: (
                (_ for _ in ()).throw(ModuleNotFoundError(name="telegram"))
                if name == "agentos.adapters.plugins.telegram.channel"
                else original_import(name, *args, **kwargs)
            ),
        ):
            await register(api)
        assert registry._pending_channels == []
        assert registry._plugin_states["telegram"]["status"] == "failed"
        assert registry._plugin_states["telegram"]["error"] == "未安装依赖: python-telegram-bot"

    @pytest.mark.asyncio
    async def test_channel_config_passthrough(self):
        api = _make_plugin_api(
            {
                "enabled": True,
                "mode": "webhook",
                "group_policy": "open",
                "group_chat_allowlist": ["-100123"],
                "require_mention": False,
            }
        )
        registry = api._registry
        await register(api)
        channel = registry._pending_channels[0]
        assert channel._config.mode == "webhook"
        assert channel._config.group_policy == "open"
        assert channel._config.group_chat_allowlist == ["-100123"]
        assert channel._config.require_mention is False
