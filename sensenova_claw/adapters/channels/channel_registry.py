"""ChannelRegistry — plugin 贡献的 Channel 条目。

P1 引入这个类的唯一动机：满足 PluginLoader.install_into_registries 的接口契约。
真正的 channel 启动（websocket / feishu / slack）在 P2 之后接入。
"""
from __future__ import annotations

from sensenova_claw.platform.plugins import RegistryEntry


class ChannelRegistry:
    """plugin 贡献的 Channel 条目存储。"""

    def __init__(self) -> None:
        self._entries: dict[str, RegistryEntry] = {}

    def register_from_plugin(self, entry: RegistryEntry) -> None:
        """同 id 覆盖。"""
        self._entries[entry.id] = entry

    def get(self, entry_id: str) -> RegistryEntry | None:
        return self._entries.get(entry_id)

    def get_all(self) -> list[RegistryEntry]:
        return list(self._entries.values())
