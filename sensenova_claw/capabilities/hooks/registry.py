"""HookRegistry — 收集 plugin 贡献的 hook 条目，给 P6 的 HookPipeline 消费。

P1 阶段：只做 (id -> entry) 的字典存储。
P6 阶段：HookPipeline 会按 metadata['event'] 索引并 spawn 子进程。
"""
from __future__ import annotations

from sensenova_claw.platform.plugins import RegistryEntry


class HookRegistry:
    """plugin 贡献的 hook 条目存储。"""

    def __init__(self) -> None:
        self._entries: dict[str, RegistryEntry] = {}

    def register_from_plugin(self, entry: RegistryEntry) -> None:
        """注入一条 plugin contribution。同 id 覆盖旧值。"""
        self._entries[entry.id] = entry

    def get(self, entry_id: str) -> RegistryEntry | None:
        return self._entries.get(entry_id)

    def get_all(self) -> list[RegistryEntry]:
        return list(self._entries.values())
