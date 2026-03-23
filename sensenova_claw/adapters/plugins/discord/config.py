"""Discord 插件配置。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from sensenova_claw.adapters.plugins.base import PluginApi


@dataclass
class DiscordConfig:
    """Discord 插件配置。"""

    enabled: bool = False
    bot_token: str = ""
    dm_policy: Literal["open", "allowlist", "disabled"] = "open"
    group_policy: Literal["open", "allowlist", "disabled"] = "allowlist"
    allowlist: list[str] = field(default_factory=list)
    group_allowlist: list[str] = field(default_factory=list)
    channel_allowlist: list[str] = field(default_factory=list)
    require_mention: bool = True
    show_tool_progress: bool = False
    reply_in_thread: bool = True

    @classmethod
    def from_plugin_api(cls, api: PluginApi) -> "DiscordConfig":
        return cls(
            enabled=api.get_config("enabled", False),
            bot_token=api.get_config("bot_token", ""),
            dm_policy=api.get_config("dm_policy", "open"),
            group_policy=api.get_config("group_policy", "allowlist"),
            allowlist=api.get_config("allowlist", []),
            group_allowlist=api.get_config("group_allowlist", []),
            channel_allowlist=api.get_config("channel_allowlist", []),
            require_mention=api.get_config("require_mention", True),
            show_tool_progress=api.get_config("show_tool_progress", False),
            reply_in_thread=api.get_config("reply_in_thread", True),
        )

