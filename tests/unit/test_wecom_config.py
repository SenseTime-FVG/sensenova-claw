"""企微配置 WecomConfig 单元测试"""

from __future__ import annotations

from unittest.mock import MagicMock

from sensenova_claw.adapters.plugins.wecom.config import WecomConfig


class TestWecomConfigDefaults:
    """测试 WecomConfig 默认值"""

    def test_default_values(self):
        cfg = WecomConfig()
        assert cfg.enabled is False
        assert cfg.bot_id == ""
        assert cfg.secret == ""
        assert cfg.websocket_url == "wss://openws.work.weixin.qq.com"
        assert cfg.dm_policy == "open"
        assert cfg.group_policy == "open"
        assert cfg.allowlist == []
        assert cfg.group_allowlist == []
        assert cfg.show_tool_progress is False


class TestWecomConfigFromPluginApi:
    """测试 from_plugin_api 工厂方法"""

    def _make_api(self, overrides: dict | None = None) -> MagicMock:
        defaults = {
            "enabled": True,
            "bot_id": "bot_001",
            "secret": "secret_001",
            "websocket_url": "wss://example.invalid",
            "dm_policy": "allowlist",
            "group_policy": "allowlist",
            "allowlist": ["u1"],
            "group_allowlist": ["g1"],
            "show_tool_progress": True,
        }
        if overrides:
            defaults.update(overrides)

        api = MagicMock()
        api.get_config.side_effect = lambda key, default=None: defaults.get(key, default)
        return api

    def test_from_plugin_api_full(self):
        api = self._make_api()
        cfg = WecomConfig.from_plugin_api(api)
        assert cfg.enabled is True
        assert cfg.bot_id == "bot_001"
        assert cfg.secret == "secret_001"
        assert cfg.websocket_url == "wss://example.invalid"
        assert cfg.dm_policy == "allowlist"
        assert cfg.group_policy == "allowlist"
        assert cfg.allowlist == ["u1"]
        assert cfg.group_allowlist == ["g1"]
        assert cfg.show_tool_progress is True

    def test_from_plugin_api_defaults(self):
        api = MagicMock()
        api.get_config.side_effect = lambda key, default=None: default
        cfg = WecomConfig.from_plugin_api(api)
        assert cfg.enabled is False
        assert cfg.bot_id == ""
        assert cfg.secret == ""
        assert cfg.websocket_url == "wss://openws.work.weixin.qq.com"
        assert cfg.dm_policy == "open"
        assert cfg.group_policy == "open"
        assert cfg.allowlist == []
        assert cfg.group_allowlist == []
        assert cfg.show_tool_progress is False
