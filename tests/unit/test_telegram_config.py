"""Telegram 配置单元测试。"""

from __future__ import annotations

import pytest
telegram = pytest.importorskip("telegram", reason="python-telegram-bot not installed")

from unittest.mock import MagicMock

from sensenova_claw.adapters.plugins.telegram.config import TelegramConfig


class TestTelegramConfigDefaults:
    def test_default_values(self):
        cfg = TelegramConfig()
        assert cfg.enabled is False
        assert cfg.bot_token == ""
        assert cfg.mode == "polling"
        assert cfg.dm_policy == "open"
        assert cfg.group_policy == "allowlist"
        assert cfg.allowlist == []
        assert cfg.group_allowlist == []
        assert cfg.group_chat_allowlist == []
        assert cfg.require_mention is True
        assert cfg.show_tool_progress is False
        assert cfg.reply_to_message is True
        assert cfg.polling_timeout_seconds == 30
        assert cfg.webhook_url == ""
        assert cfg.webhook_secret == ""
        assert cfg.webhook_path == "/telegram-webhook"
        assert cfg.webhook_host == "127.0.0.1"
        assert cfg.webhook_port == 8787


class TestTelegramConfigFromPluginApi:
    def _make_api(self, overrides: dict | None = None) -> MagicMock:
        defaults = {
            "enabled": True,
            "bot_token": "123:abc",
            "mode": "webhook",
            "dm_policy": "allowlist",
            "group_policy": "open",
            "allowlist": ["1001"],
            "group_allowlist": ["1002"],
            "group_chat_allowlist": ["-100123"],
            "require_mention": False,
            "show_tool_progress": True,
            "reply_to_message": False,
            "polling_timeout_seconds": 15,
            "webhook_url": "https://example.com/telegram",
            "webhook_secret": "secret",
            "webhook_path": "/custom-hook",
            "webhook_host": "0.0.0.0",
            "webhook_port": 9000,
        }
        if overrides:
            defaults.update(overrides)

        api = MagicMock()
        api.get_config.side_effect = lambda key, default=None: defaults.get(key, default)
        return api

    def test_from_plugin_api_full(self):
        api = self._make_api()
        cfg = TelegramConfig.from_plugin_api(api)
        assert cfg.enabled is True
        assert cfg.bot_token == "123:abc"
        assert cfg.mode == "webhook"
        assert cfg.dm_policy == "allowlist"
        assert cfg.group_policy == "open"
        assert cfg.allowlist == ["1001"]
        assert cfg.group_allowlist == ["1002"]
        assert cfg.group_chat_allowlist == ["-100123"]
        assert cfg.require_mention is False
        assert cfg.show_tool_progress is True
        assert cfg.reply_to_message is False
        assert cfg.polling_timeout_seconds == 15
        assert cfg.webhook_url == "https://example.com/telegram"
        assert cfg.webhook_secret == "secret"
        assert cfg.webhook_path == "/custom-hook"
        assert cfg.webhook_host == "0.0.0.0"
        assert cfg.webhook_port == 9000

    def test_from_plugin_api_defaults(self):
        api = MagicMock()
        api.get_config.side_effect = lambda key, default=None: default
        cfg = TelegramConfig.from_plugin_api(api)
        assert cfg.enabled is False
        assert cfg.bot_token == ""
        assert cfg.mode == "polling"
        assert cfg.dm_policy == "open"
        assert cfg.group_policy == "allowlist"
        assert cfg.allowlist == []
        assert cfg.group_allowlist == []
        assert cfg.group_chat_allowlist == []
        assert cfg.require_mention is True
        assert cfg.show_tool_progress is False
        assert cfg.reply_to_message is True
        assert cfg.polling_timeout_seconds == 30
