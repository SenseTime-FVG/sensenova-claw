"""Telegram 插件配置。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from agentos.adapters.plugins.base import PluginApi


@dataclass
class TelegramConfig:
    """Telegram 插件配置。"""

    enabled: bool = False
    bot_token: str = ""
    mode: Literal["polling", "webhook"] = "polling"
    dm_policy: Literal["open", "allowlist", "disabled"] = "open"
    group_policy: Literal["open", "allowlist", "disabled"] = "allowlist"
    allowlist: list[str] = field(default_factory=list)
    group_allowlist: list[str] = field(default_factory=list)
    group_chat_allowlist: list[str] = field(default_factory=list)
    require_mention: bool = True
    show_tool_progress: bool = False
    reply_to_message: bool = True
    polling_timeout_seconds: int = 30
    webhook_url: str = ""
    webhook_secret: str = ""
    webhook_path: str = "/telegram-webhook"
    webhook_host: str = "127.0.0.1"
    webhook_port: int = 8787

    @classmethod
    def from_plugin_api(cls, api: PluginApi) -> "TelegramConfig":
        return cls(
            enabled=api.get_config("enabled", False),
            bot_token=api.get_config("bot_token", ""),
            mode=api.get_config("mode", "polling"),
            dm_policy=api.get_config("dm_policy", "open"),
            group_policy=api.get_config("group_policy", "allowlist"),
            allowlist=api.get_config("allowlist", []),
            group_allowlist=api.get_config("group_allowlist", []),
            group_chat_allowlist=api.get_config("group_chat_allowlist", []),
            require_mention=api.get_config("require_mention", True),
            show_tool_progress=api.get_config("show_tool_progress", False),
            reply_to_message=api.get_config("reply_to_message", True),
            polling_timeout_seconds=int(api.get_config("polling_timeout_seconds", 30)),
            webhook_url=api.get_config("webhook_url", ""),
            webhook_secret=api.get_config("webhook_secret", ""),
            webhook_path=api.get_config("webhook_path", "/telegram-webhook"),
            webhook_host=api.get_config("webhook_host", "127.0.0.1"),
            webhook_port=int(api.get_config("webhook_port", 8787)),
        )
