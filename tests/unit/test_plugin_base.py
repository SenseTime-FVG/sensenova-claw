"""Plugin 基础类型单元测试（无 mock，使用真实组件）"""

import pytest

from agentos.adapters.plugins.base import PluginDefinition, PluginApi
from agentos.adapters.plugins import PluginRegistry
from agentos.adapters.channels.base import Channel
from agentos.capabilities.tools.base import Tool
from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.runtime.publisher import EventPublisher
from agentos.interfaces.ws.gateway import Gateway
from agentos.platform.config.config import Config


# ---------- 轻量真实 Channel / Tool ----------


class StubChannel(Channel):
    """测试用轻量 Channel"""

    def __init__(self, channel_id: str = "stub-ch"):
        self._channel_id = channel_id

    def get_channel_id(self) -> str:
        return self._channel_id

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send_event(self, event: EventEnvelope) -> None:
        pass


class StubTool(Tool):
    """测试用轻量 Tool"""
    name = "stub-tool"
    description = "stub"

    async def execute(self, **kwargs):
        return "ok"


# ---------- PluginDefinition 测试 ----------


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


# ---------- PluginApi 测试（使用真实 PluginRegistry / Gateway / Config） ----------


class TestPluginApi:
    """PluginApi 接口测试"""

    @pytest.fixture
    def registry(self):
        """真实 PluginRegistry"""
        return PluginRegistry()

    @pytest.fixture
    def bus(self):
        return PublicEventBus()

    @pytest.fixture
    def publisher(self, bus):
        return EventPublisher(bus=bus)

    @pytest.fixture
    def gateway(self, publisher):
        return Gateway(publisher=publisher)

    @pytest.fixture
    def ready_registry(self, registry, gateway, publisher):
        """已设置 gateway/publisher 引用的 PluginRegistry"""
        registry._gateway = gateway
        registry._publisher = publisher
        return registry

    @pytest.fixture
    def api(self, ready_registry):
        return PluginApi(plugin_id="test-plugin", registry=ready_registry)

    def test_init(self, api):
        """初始化属性"""
        assert api.plugin_id == "test-plugin"

    def test_register_channel(self, api, ready_registry):
        """注册真实 Channel"""
        channel = StubChannel("ch-1")
        api.register_channel(channel)
        assert channel in ready_registry._pending_channels
        assert len(ready_registry._pending_channels) == 1

    def test_register_multiple_channels(self, api, ready_registry):
        """注册多个 Channel"""
        ch1 = StubChannel("ch-1")
        ch2 = StubChannel("ch-2")
        api.register_channel(ch1)
        api.register_channel(ch2)
        assert len(ready_registry._pending_channels) == 2

    def test_register_tool(self, api, ready_registry):
        """注册真实 Tool"""
        tool = StubTool()
        api.register_tool(tool)
        assert tool in ready_registry._pending_tools

    def test_register_hook(self, api, ready_registry):
        """注册 Hook（预留接口）"""
        def handler(event):
            pass

        api.register_hook("agent.step_completed", handler)
        assert ("agent.step_completed", handler) in ready_registry._pending_hooks

    def test_get_config(self, tmp_path):
        """通过真实 Config 读取插件配置"""
        # 写入临时配置文件
        config_yml = tmp_path / "config.yml"
        config_yml.write_text(
            "plugins:\n  test-plugin:\n    api_key: value123\n",
            encoding="utf-8",
        )
        cfg = Config(config_path=config_yml)

        # 临时替换全局 config 对象
        import agentos.platform.config.config as config_module
        original = config_module.config
        config_module.config = cfg
        try:
            registry = PluginRegistry()
            api = PluginApi(plugin_id="test-plugin", registry=registry)
            result = api.get_config("api_key")
            assert result == "value123"
        finally:
            config_module.config = original

    def test_get_config_with_default(self, tmp_path):
        """读取不存在的配置项返回默认值"""
        config_yml = tmp_path / "config.yml"
        config_yml.write_text("", encoding="utf-8")
        cfg = Config(config_path=config_yml)

        import agentos.platform.config.config as config_module
        original = config_module.config
        config_module.config = cfg
        try:
            registry = PluginRegistry()
            api = PluginApi(plugin_id="test-plugin", registry=registry)
            result = api.get_config("timeout", default=30)
            assert result == 30
        finally:
            config_module.config = original

    def test_get_gateway(self, api, gateway):
        """获取 Gateway"""
        gw = api.get_gateway()
        assert gw is gateway

    def test_get_publisher(self, api, publisher):
        """获取 EventPublisher"""
        pub = api.get_publisher()
        assert pub is publisher
