"""Plugin 系统基础类型：PluginDefinition 和 PluginApi"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from agentos.adapters.channels.base import Channel
    from agentos.interfaces.ws.gateway import Gateway
    from agentos.adapters.plugins import PluginRegistry
    from agentos.kernel.runtime.publisher import EventPublisher
    from agentos.capabilities.tools.base import Tool


@dataclass
class PluginDefinition:
    """插件元信息"""

    id: str  # 唯一标识，如 "feishu"
    name: str  # 显示名称
    version: str = "0.1.0"
    description: str = ""


def format_missing_dependency_error(exc: ImportError, package_hint: str = "") -> str:
    """将 ImportError 规范化为 Gateway 可展示的缺依赖提示。"""
    package = package_hint.strip()
    if not package and isinstance(exc, ModuleNotFoundError):
        package = str(getattr(exc, "name", "")).strip()
    if not package:
        message = str(exc).strip() or type(exc).__name__
        return f"依赖导入失败: {message}"
    return f"未安装依赖: {package}"


class PluginApi:
    """
    框架传给 Plugin 的注册接口（门面模式）。
    Plugin 通过此对象注册 Channel/Tool/Hook，并访问受限的框架服务。
    """

    def __init__(self, plugin_id: str, registry: PluginRegistry):
        self.plugin_id = plugin_id
        self._registry = registry

    def register_channel(self, channel: Channel) -> None:
        """注册一个 Channel"""
        self._registry._pending_channels.append(channel)
        self._registry._plugin_states.setdefault(self.plugin_id, {})
        self._registry._plugin_states[self.plugin_id]["registered_channel_id"] = channel.get_channel_id()
        self._registry._plugin_states[self.plugin_id]["status"] = "registered"
        self._registry._plugin_states[self.plugin_id]["error"] = ""

    def register_tool(self, tool: Tool) -> None:
        """注册一个 Tool"""
        self._registry._pending_tools.append(tool)

    def register_hook(self, event_type: str, handler: Callable) -> None:
        """v0.7 预留接口，不实现 hook 分发"""
        self._registry._pending_hooks.append((event_type, handler))

    def report_status(self, status: str, *, error: str = "") -> None:
        """上报插件状态，供 Gateway 页面展示。"""
        self._registry._plugin_states.setdefault(self.plugin_id, {})
        self._registry._plugin_states[self.plugin_id]["status"] = status
        self._registry._plugin_states[self.plugin_id]["error"] = error

    def get_config(self, key: str, default: Any = None) -> Any:
        """读取 config.yaml 中 plugins.<plugin_id>.<key>"""
        from agentos.platform.config.config import config

        return config.get(f"plugins.{self.plugin_id}.{key}", default)

    def get_gateway(self) -> Gateway:
        """获取 Gateway 引用（apply() 后可用）"""
        return self._registry._gateway

    def get_publisher(self) -> EventPublisher:
        """获取 EventPublisher 引用"""
        return self._registry._publisher
