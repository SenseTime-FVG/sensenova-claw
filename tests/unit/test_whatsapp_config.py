"""WhatsApp 配置单元测试。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from agentos.adapters.plugins.whatsapp.config import WhatsAppBridgeConfig, WhatsAppConfig


class TestWhatsAppConfigDefaults:
    def test_default_values(self):
        cfg = WhatsAppConfig()
        assert cfg.enabled is False
        assert cfg.auth_dir == ""
        assert cfg.typing_indicator == "composing"
        assert cfg.dm_policy == "open"
        assert cfg.group_policy == "open"
        assert cfg.allowlist == []
        assert cfg.group_allowlist == []
        assert cfg.show_tool_progress is False
        assert isinstance(cfg.bridge, WhatsAppBridgeConfig)
        assert cfg.bridge.command == "node"


class TestWhatsAppConfigFromPluginApi:
    def _make_api(self, overrides: dict | None = None) -> MagicMock:
        defaults = {
            "enabled": True,
            "auth_dir": "/tmp/agentos-whatsapp-auth",
            "typing_indicator": "none",
            "dm_policy": "allowlist",
            "group_policy": "allowlist",
            "allowlist": ["+15550000001"],
            "group_allowlist": ["1203630@g.us"],
            "show_tool_progress": True,
            "bridge": {
                "command": "node-custom",
                "entry": "/tmp/bridge/index.mjs",
                "startup_timeout_seconds": 12,
                "send_timeout_seconds": 7,
            },
        }
        if overrides:
            defaults.update(overrides)

        api = MagicMock()
        api.get_config.side_effect = lambda key, default=None: defaults.get(key, default)
        return api

    def test_from_plugin_api_full(self):
        api = self._make_api()
        cfg = WhatsAppConfig.from_plugin_api(api)
        assert cfg.enabled is True
        assert Path(cfg.auth_dir) == Path("/tmp/agentos-whatsapp-auth").resolve()
        assert cfg.typing_indicator == "none"
        assert cfg.dm_policy == "allowlist"
        assert cfg.group_policy == "allowlist"
        assert cfg.allowlist == ["+15550000001"]
        assert cfg.group_allowlist == ["1203630@g.us"]
        assert cfg.show_tool_progress is True
        assert cfg.bridge.command == "node-custom"
        assert cfg.bridge.entry == "/tmp/bridge/index.mjs"
        assert cfg.bridge.startup_timeout_seconds == 12
        assert cfg.bridge.send_timeout_seconds == 7

    def test_from_plugin_api_defaults(self):
        api = MagicMock()
        api.get_config.side_effect = lambda key, default=None: default
        cfg = WhatsAppConfig.from_plugin_api(api)
        assert cfg.enabled is False
        assert cfg.auth_dir == ""
        assert cfg.typing_indicator == "composing"
        assert cfg.dm_policy == "open"
        assert cfg.group_policy == "open"
        assert cfg.allowlist == []
        assert cfg.group_allowlist == []
        assert cfg.show_tool_progress is False
        assert cfg.bridge.command == "node"

    def test_from_plugin_api_resolves_relative_auth_dir_to_absolute(self):
        api = self._make_api({"auth_dir": ".agentos/data/plugins/whatsapp/auth"})
        cfg = WhatsAppConfig.from_plugin_api(api)
        assert Path(cfg.auth_dir).is_absolute()

    def test_from_plugin_api_remaps_legacy_bridge_entry_to_plugins_path(self):
        api = self._make_api(
            {
                "bridge": {
                    "command": "node",
                    "entry": "agentos/adapters/channels/whatsapp/bridge/src/index.mjs",
                    "startup_timeout_seconds": 30,
                    "send_timeout_seconds": 15,
                }
            }
        )
        cfg = WhatsAppConfig.from_plugin_api(api)
        assert cfg.bridge.entry.endswith(
            "agentos/adapters/plugins/whatsapp/bridge/src/index.mjs"
        )
