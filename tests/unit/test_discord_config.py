"""Discord 配置单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

from agentos.adapters.plugins.discord.config import DiscordConfig


class TestDiscordConfigDefaults:
    def test_default_values(self):
        cfg = DiscordConfig()
        assert cfg.enabled is False
        assert cfg.bot_token == ""
        assert cfg.dm_policy == "open"
        assert cfg.group_policy == "allowlist"
        assert cfg.allowlist == []
        assert cfg.group_allowlist == []
        assert cfg.channel_allowlist == []
        assert cfg.require_mention is True
        assert cfg.show_tool_progress is False
        assert cfg.reply_in_thread is True


class TestDiscordConfigFromPluginApi:
    def _make_api(self, overrides: dict | None = None) -> MagicMock:
        defaults = {
            "enabled": True,
            "bot_token": "discord-token",
            "dm_policy": "allowlist",
            "group_policy": "allowlist",
            "allowlist": ["user-1"],
            "group_allowlist": ["user-2"],
            "channel_allowlist": ["channel-1", "thread-1"],
            "require_mention": False,
            "show_tool_progress": True,
            "reply_in_thread": False,
        }
        if overrides:
            defaults.update(overrides)

        api = MagicMock()
        api.get_config.side_effect = lambda key, default=None: defaults.get(key, default)
        return api

    def test_from_plugin_api_full(self):
        cfg = DiscordConfig.from_plugin_api(self._make_api())
        assert cfg.enabled is True
        assert cfg.bot_token == "discord-token"
        assert cfg.dm_policy == "allowlist"
        assert cfg.group_policy == "allowlist"
        assert cfg.allowlist == ["user-1"]
        assert cfg.group_allowlist == ["user-2"]
        assert cfg.channel_allowlist == ["channel-1", "thread-1"]
        assert cfg.require_mention is False
        assert cfg.show_tool_progress is True
        assert cfg.reply_in_thread is False

    def test_from_plugin_api_defaults(self):
        api = MagicMock()
        api.get_config.side_effect = lambda key, default=None: default
        cfg = DiscordConfig.from_plugin_api(api)
        assert cfg.enabled is False
        assert cfg.bot_token == ""
        assert cfg.group_policy == "allowlist"
        assert cfg.channel_allowlist == []
