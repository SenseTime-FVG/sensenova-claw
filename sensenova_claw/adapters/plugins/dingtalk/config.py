"""DingTalk 插件配置。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from sensenova_claw.adapters.plugins.base import PluginApi


@dataclass
class DingtalkConfig:
    """DingTalk 插件配置。"""

    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""
    dm_policy: Literal["open", "allowlist", "disabled"] = "open"
    group_policy: Literal["open", "allowlist", "disabled"] = "open"
    allowlist: list[str] = field(default_factory=list)
    group_allowlist: list[str] = field(default_factory=list)
    require_mention: bool = True
    show_tool_progress: bool = False
    reply_to_sender: bool = False

    @classmethod
    def from_plugin_api(cls, api: PluginApi) -> "DingtalkConfig":
        return cls(
            enabled=api.get_config("enabled", False),
            client_id=api.get_config("client_id", ""),
            client_secret=api.get_config("client_secret", ""),
            dm_policy=api.get_config("dm_policy", "open"),
            group_policy=api.get_config("group_policy", "open"),
            allowlist=api.get_config("allowlist", []),
            group_allowlist=api.get_config("group_allowlist", []),
            require_mention=api.get_config("require_mention", True),
            show_tool_progress=api.get_config("show_tool_progress", False),
            reply_to_sender=api.get_config("reply_to_sender", False),
        )
