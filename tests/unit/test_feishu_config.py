"""飞书配置 FeishuConfig 单元测试"""

from __future__ import annotations

from unittest.mock import MagicMock

from agentos.adapters.channels.feishu.config import FeishuConfig


class TestFeishuConfigDefaults:
    """测试 FeishuConfig 默认值"""

    def test_default_values(self):
        cfg = FeishuConfig()
        assert cfg.enabled is False
        assert cfg.app_id == ""
        assert cfg.app_secret == ""
        assert cfg.dm_policy == "open"
        assert cfg.group_policy == "mention"
        assert cfg.allowlist == []
        assert cfg.log_level == "INFO"
        assert cfg.render_mode == "card"
        assert cfg.show_tool_progress is False

    def test_custom_values(self):
        cfg = FeishuConfig(
            enabled=True,
            app_id="app123",
            app_secret="secret456",
            dm_policy="allowlist",
            group_policy="open",
            allowlist=["user1", "user2"],
            log_level="DEBUG",
            render_mode="text",
            show_tool_progress=True,
        )
        assert cfg.enabled is True
        assert cfg.app_id == "app123"
        assert cfg.app_secret == "secret456"
        assert cfg.dm_policy == "allowlist"
        assert cfg.group_policy == "open"
        assert cfg.allowlist == ["user1", "user2"]
        assert cfg.log_level == "DEBUG"
        assert cfg.render_mode == "text"
        assert cfg.show_tool_progress is True


class TestFeishuConfigFromPluginApi:
    """测试 from_plugin_api 工厂方法"""

    def _make_api(self, overrides: dict | None = None) -> MagicMock:
        """构造一个 mock PluginApi，支持 get_config"""
        defaults = {
            "enabled": True,
            "app_id": "id_001",
            "app_secret": "sec_001",
            "dm_policy": "allowlist",
            "group_policy": "disabled",
            "allowlist": ["u1"],
            "log_level": "DEBUG",
            "render_mode": "text",
            "show_tool_progress": True,
        }
        if overrides:
            defaults.update(overrides)

        api = MagicMock()
        api.get_config.side_effect = lambda key, default=None: defaults.get(key, default)
        return api

    def test_from_plugin_api_full(self):
        """完整配置应全部正确传递"""
        api = self._make_api()
        cfg = FeishuConfig.from_plugin_api(api)
        assert cfg.enabled is True
        assert cfg.app_id == "id_001"
        assert cfg.app_secret == "sec_001"
        assert cfg.dm_policy == "allowlist"
        assert cfg.group_policy == "disabled"
        assert cfg.allowlist == ["u1"]
        assert cfg.log_level == "DEBUG"
        assert cfg.render_mode == "text"
        assert cfg.show_tool_progress is True

    def test_from_plugin_api_defaults(self):
        """未配置的 key 应回退到默认值"""
        api = MagicMock()
        # get_config 总是返回 default 参数
        api.get_config.side_effect = lambda key, default=None: default
        cfg = FeishuConfig.from_plugin_api(api)
        assert cfg.enabled is False
        assert cfg.app_id == ""
        assert cfg.app_secret == ""
        assert cfg.dm_policy == "open"
        assert cfg.group_policy == "mention"
        assert cfg.allowlist == []
        assert cfg.log_level == "INFO"
        assert cfg.render_mode == "card"
        assert cfg.show_tool_progress is False
