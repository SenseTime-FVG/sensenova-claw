"""CommandRegistry — 收集 plugin 贡献的斜杠命令。

P1：占位空 Registry。后续由命令分发器消费 metadata['path'] 指向的 Markdown。
"""
from __future__ import annotations

from sensenova_claw.platform.plugins import RegistryEntry


class CommandRegistry:
    """plugin 贡献的命令条目存储。"""

    def __init__(self) -> None:
        self._entries: dict[str, RegistryEntry] = {}

    def register_from_plugin(self, entry: RegistryEntry) -> None:
        self._entries[entry.id] = entry

    def get(self, entry_id: str) -> RegistryEntry | None:
        return self._entries.get(entry_id)

    def get_all(self) -> list[RegistryEntry]:
        return list(self._entries.values())
