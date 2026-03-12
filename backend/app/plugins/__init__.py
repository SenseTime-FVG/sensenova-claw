"""Plugin 系统：注册表和加载器"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from app.gateway.base import Channel
    from app.gateway.gateway import Gateway
    from app.runtime.publisher import EventPublisher
    from app.tools.base import Tool
    from app.tools.registry import ToolRegistry

    from app.plugins.base import PluginDefinition

logger = logging.getLogger(__name__)


class PluginRegistry:
    """插件注册表：发现、加载、管理所有 Plugin"""

    def __init__(self):
        self._plugins: dict[str, PluginDefinition] = {}
        self._pending_channels: list[Channel] = []
        self._pending_tools: list[Tool] = []
        self._pending_hooks: list[tuple[str, Callable]] = []
        self._gateway: Gateway | None = None
        self._publisher: EventPublisher | None = None

    async def load_plugins(
        self,
        config: dict[str, Any],
        gateway: Gateway | None = None,
        publisher: EventPublisher | None = None,
    ) -> None:
        """
        扫描并加载所有启用的 Plugin。
        加载顺序: 内置插件(app/plugins/*/) → 用户插件(~/.agentos/plugins/*/)
        错误处理: 缺少 definition/register 跳过+警告；register() 异常跳过+错误日志；id 冲突后者覆盖
        """
        # 提前设置引用，使 register() 内可通过 api.get_gateway() 等获取
        if gateway is not None:
            self._gateway = gateway
        if publisher is not None:
            self._publisher = publisher

        from app.plugins.base import PluginApi

        # 扫描内置插件目录
        plugins_dir = Path(__file__).parent
        for finder, name, is_pkg in pkgutil.iter_modules([str(plugins_dir)]):
            if not is_pkg:
                continue
            if name.startswith("_"):
                continue

            module_name = f"app.plugins.{name}.plugin"
            try:
                module = importlib.import_module(module_name)
            except ImportError:
                logger.warning("Plugin '%s' 缺少 plugin.py，跳过", name)
                continue
            except Exception:
                logger.exception("加载 Plugin '%s' 失败", name)
                continue

            definition = getattr(module, "definition", None)
            register_fn = getattr(module, "register", None)

            if definition is None or register_fn is None:
                logger.warning("Plugin '%s' 缺少 definition 或 register，跳过", name)
                continue

            plugin_id = definition.id
            if plugin_id in self._plugins:
                logger.warning("Plugin id '%s' 冲突，后者覆盖", plugin_id)

            self._plugins[plugin_id] = definition
            api = PluginApi(plugin_id=plugin_id, registry=self)

            try:
                await register_fn(api)
                logger.info("Plugin '%s' v%s 加载成功", definition.name, definition.version)
            except Exception:
                logger.exception("Plugin '%s' register() 执行失败", plugin_id)
                self._plugins.pop(plugin_id, None)

    async def apply(
        self,
        gateway: Gateway,
        tool_registry: ToolRegistry,
        publisher: EventPublisher,
    ) -> None:
        """将收集到的 Channel/Tool/Hook 注入到框架中"""
        self._gateway = gateway
        self._publisher = publisher

        for channel in self._pending_channels:
            gateway.register_channel(channel)
            logger.info("Plugin Channel '%s' 已注册到 Gateway", channel.get_channel_id())

        for tool in self._pending_tools:
            tool_registry.register(tool)
            logger.info("Plugin Tool '%s' 已注册到 ToolRegistry", tool.name)
