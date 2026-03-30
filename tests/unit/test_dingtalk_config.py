"""DingTalk 配置单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

from sensenova_claw.adapters.plugins.dingtalk.config import DingtalkConfig


class TestDingtalkConfigDefaults:
    def test_default_values(self):
        cfg = DingtalkConfig()
        assert cfg.enabled is False
        assert cfg.client_id == ""
        assert cfg.client_secret == ""
        assert cfg.dm_policy == "open"
        assert cfg.group_policy == "open"
        assert cfg.allowlist == []
        assert cfg.group_allowlist == []
        assert cfg.require_mention is True
        assert cfg.show_tool_progress is False
        assert cfg.reply_to_sender is False


class TestDingtalkConfigFromPluginApi:
    def _make_api(self, overrides: dict | None = None) -> MagicMock:
        defaults = {
            "enabled": True,
            "client_id": "ding-app-key",
            "client_secret": "ding-app-secret",
            "dm_policy": "allowlist",
            "group_policy": "allowlist",
            "allowlist": ["staff-1"],
            "group_allowlist": ["staff-2"],
            "require_mention": False,
            "show_tool_progress": True,
            "reply_to_sender": True,
        }
        if overrides:
            defaults.update(overrides)

        api = MagicMock()
        api.get_config.side_effect = lambda key, default=None: defaults.get(key, default)
        return api

    def test_from_plugin_api_full(self):
        api = self._make_api()
        cfg = DingtalkConfig.from_plugin_api(api)
        assert cfg.enabled is True
        assert cfg.client_id == "ding-app-key"
        assert cfg.client_secret == "ding-app-secret"
        assert cfg.dm_policy == "allowlist"
        assert cfg.group_policy == "allowlist"
        assert cfg.allowlist == ["staff-1"]
        assert cfg.group_allowlist == ["staff-2"]
        assert cfg.require_mention is False
        assert cfg.show_tool_progress is True
        assert cfg.reply_to_sender is True

    def test_from_plugin_api_defaults(self):
        api = MagicMock()
        api.get_config.side_effect = lambda key, default=None: default
        cfg = DingtalkConfig.from_plugin_api(api)
        assert cfg.enabled is False
        assert cfg.client_id == ""
        assert cfg.client_secret == ""
        assert cfg.dm_policy == "open"
        assert cfg.group_policy == "open"
        assert cfg.allowlist == []
        assert cfg.group_allowlist == []
        assert cfg.require_mention is True
        assert cfg.show_tool_progress is False
        assert cfg.reply_to_sender is False
