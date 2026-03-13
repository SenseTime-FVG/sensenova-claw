"""飞书插件入口 plugin.py 单元测试

验证：
- PluginDefinition 元信息
- register() 函数：启用/禁用行为、Channel/Tool 注册
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentos.adapters.channels.feishu.plugin import definition, register


# ---- PluginDefinition 测试 ----


class TestPluginDefinition:
    def test_id(self):
        assert definition.id == "feishu"

    def test_name(self):
        assert definition.name == "飞书"

    def test_version(self):
        assert definition.version == "0.9.0"

    def test_description_not_empty(self):
        assert len(definition.description) > 0


# ---- register() 测试 ----


def _make_api(overrides: dict | None = None) -> MagicMock:
    """构造 mock PluginApi"""
    defaults = {
        "enabled": False,
        "app_id": "test_app",
        "app_secret": "test_secret",
        "dm_policy": "open",
        "group_policy": "mention",
        "allowlist": [],
        "log_level": "INFO",
        "render_mode": "card",
        "show_tool_progress": False,
        "api_tool": {},
    }
    if overrides:
        defaults.update(overrides)

    api = MagicMock()
    api.get_config.side_effect = lambda key, default=None: defaults.get(key, default)
    api.register_channel = MagicMock()
    api.register_tool = MagicMock()
    api.get_gateway = MagicMock()
    api.get_publisher = MagicMock()
    return api


class TestRegister:
    async def test_disabled_does_nothing(self):
        """enabled=False 时不应注册任何 Channel 或 Tool"""
        api = _make_api({"enabled": False})
        await register(api)
        api.register_channel.assert_not_called()
        api.register_tool.assert_not_called()

    async def test_enabled_registers_channel(self):
        """enabled=True 时应注册 FeishuChannel"""
        api = _make_api({"enabled": True})
        await register(api)
        api.register_channel.assert_called_once()
        # 注册的应该是 FeishuChannel 实例
        channel = api.register_channel.call_args[0][0]
        assert channel.get_channel_id() == "feishu"

    async def test_enabled_registers_message_tool(self):
        """enabled=True 时应注册 MessageTool"""
        api = _make_api({"enabled": True})
        await register(api)
        # register_tool 至少被调用一次（MessageTool）
        assert api.register_tool.call_count >= 1

    async def test_api_tool_disabled_by_default(self):
        """默认不启用 api_tool 时，只注册 MessageTool（1 次）"""
        api = _make_api({"enabled": True, "api_tool": {}})
        await register(api)
        assert api.register_tool.call_count == 1  # 仅 MessageTool

    async def test_api_tool_enabled(self):
        """api_tool.enabled=True 时应额外注册 FeishuApiTool"""
        api = _make_api({
            "enabled": True,
            "api_tool": {
                "enabled": True,
                "allowed_methods": ["GET", "POST"],
                "allowed_path_prefixes": ["/open-apis/im"],
            },
        })
        await register(api)
        # MessageTool + FeishuApiTool = 2
        assert api.register_tool.call_count == 2

    async def test_channel_config_passthrough(self):
        """Channel 应使用 FeishuConfig 中的配置值"""
        api = _make_api({
            "enabled": True,
            "app_id": "my_app",
            "app_secret": "my_secret",
            "render_mode": "text",
        })
        await register(api)
        channel = api.register_channel.call_args[0][0]
        assert channel._config.app_id == "my_app"
        assert channel._config.app_secret == "my_secret"
        assert channel._config.render_mode == "text"
