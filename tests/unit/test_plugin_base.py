"""Plugin 基础类型单元测试"""

from unittest.mock import MagicMock, patch

import pytest

from agentos.adapters.plugins.base import PluginDefinition, PluginApi


class TestPluginDefinition:
    """PluginDefinition 数据类测试"""

    def test_minimal(self):
        """最小参数创建"""
        pd = PluginDefinition(id="test", name="Test Plugin")
        assert pd.id == "test"
        assert pd.name == "Test Plugin"
        assert pd.version == "0.1.0"
        assert pd.description == ""

    def test_full(self):
        """完整参数创建"""
        pd = PluginDefinition(
            id="feishu",
            name="飞书插件",
            version="1.2.0",
            description="飞书集成插件",
        )
        assert pd.id == "feishu"
        assert pd.name == "飞书插件"
        assert pd.version == "1.2.0"
        assert pd.description == "飞书集成插件"

    def test_equality(self):
        """dataclass 默认 equality"""
        pd1 = PluginDefinition(id="a", name="A")
        pd2 = PluginDefinition(id="a", name="A")
        assert pd1 == pd2

    def test_inequality(self):
        pd1 = PluginDefinition(id="a", name="A")
        pd2 = PluginDefinition(id="b", name="B")
        assert pd1 != pd2


class TestPluginApi:
    """PluginApi 接口测试"""

    @pytest.fixture
    def mock_registry(self):
        """模拟 PluginRegistry"""
        registry = MagicMock()
        registry._pending_channels = []
        registry._pending_tools = []
        registry._pending_hooks = []
        registry._gateway = MagicMock()
        registry._publisher = MagicMock()
        return registry

    @pytest.fixture
    def api(self, mock_registry):
        return PluginApi(plugin_id="test-plugin", registry=mock_registry)

    def test_init(self, api):
        """初始化属性"""
        assert api.plugin_id == "test-plugin"

    def test_register_channel(self, api, mock_registry):
        """注册 Channel"""
        channel = MagicMock()
        api.register_channel(channel)
        assert channel in mock_registry._pending_channels
        assert len(mock_registry._pending_channels) == 1

    def test_register_multiple_channels(self, api, mock_registry):
        """注册多个 Channel"""
        ch1 = MagicMock()
        ch2 = MagicMock()
        api.register_channel(ch1)
        api.register_channel(ch2)
        assert len(mock_registry._pending_channels) == 2

    def test_register_tool(self, api, mock_registry):
        """注册 Tool"""
        tool = MagicMock()
        api.register_tool(tool)
        assert tool in mock_registry._pending_tools

    def test_register_hook(self, api, mock_registry):
        """注册 Hook（预留接口）"""
        handler = MagicMock()
        api.register_hook("agent.step_completed", handler)
        assert ("agent.step_completed", handler) in mock_registry._pending_hooks

    def test_get_config(self, api):
        """读取插件配置"""
        with patch("agentos.platform.config.config.config") as mock_config:
            mock_config.get.return_value = "value123"
            result = api.get_config("api_key")
            mock_config.get.assert_called_once_with("plugins.test-plugin.api_key", None)
            assert result == "value123"

    def test_get_config_with_default(self, api):
        """读取插件配置带默认值"""
        with patch("agentos.platform.config.config.config") as mock_config:
            mock_config.get.return_value = "fallback"
            result = api.get_config("timeout", default=30)
            mock_config.get.assert_called_once_with("plugins.test-plugin.timeout", 30)
            assert result == "fallback"

    def test_get_gateway(self, api, mock_registry):
        """获取 Gateway"""
        gw = api.get_gateway()
        assert gw is mock_registry._gateway

    def test_get_publisher(self, api, mock_registry):
        """获取 EventPublisher"""
        pub = api.get_publisher()
        assert pub is mock_registry._publisher
