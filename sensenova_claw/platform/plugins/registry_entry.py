"""RegistryEntry — Plugin 注入到各 Registry 时的统一条目结构。

冻结契约见 docs/design/2026-04-27-plan-decomposition.md §3.2。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RegistryEntry:
    """一个 plugin contribution 在 Registry 中的注册条目。

    - id: 全局唯一，格式 ``f"{plugin.id}::{contribution.id}"``。
    - short_id: plugin 内部短名，用于 plugin 内引用。
    - owner_plugin: plugin id（如 ``core/builtin-tools``）。
    - owner_team: plugin manifest 中的 owner（如 ``core`` / ``team-a``）。
    - visibility: ``public`` / ``internal`` / ``private``，P5 接入时使用。
    - impl: 实际实现引用；P1 阶段统一为 None，P2 真正实例化时填入。
    - metadata: Registry 自定义字段，例如 ``{"type": "python", "python": "..."}``。
    """

    id: str
    short_id: str
    owner_plugin: str
    owner_team: str
    visibility: str
    impl: Any
    metadata: dict[str, Any] = field(default_factory=dict)
