"""企业微信插件配置。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sensenova_claw.adapters.plugins.base import PluginApi


@dataclass
class WecomConfig:
    """企业微信插件配置。"""

    enabled: bool = False
    bot_id: str = ""
    secret: str = ""
    websocket_url: str = "wss://openws.work.weixin.qq.com"
    dm_policy: str = "open"
    group_policy: str = "open"
    allowlist: list[str] = field(default_factory=list)
    group_allowlist: list[str] = field(default_factory=list)
    show_tool_progress: bool = False

    @classmethod
    def from_plugin_api(cls, api: "PluginApi") -> "WecomConfig":
        return cls(
            enabled=api.get_config("enabled", False),
            bot_id=api.get_config("bot_id", ""),
            secret=api.get_config("secret", ""),
            websocket_url=api.get_config(
                "websocket_url", "wss://openws.work.weixin.qq.com"
            ),
            dm_policy=api.get_config("dm_policy", "open"),
            group_policy=api.get_config("group_policy", "open"),
            allowlist=api.get_config("allowlist", []),
            group_allowlist=api.get_config("group_allowlist", []),
            show_tool_progress=api.get_config("show_tool_progress", False),
        )
