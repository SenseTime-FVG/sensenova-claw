"""WhatsApp 插件配置。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentos.adapters.plugins.base import PluginApi


@dataclass
class WhatsAppBridgeConfig:
    """WhatsApp sidecar 配置。"""

    command: str = "node"
    entry: str = str(Path(__file__).resolve().parent / "bridge" / "src" / "index.mjs")
    startup_timeout_seconds: float = 30.0
    send_timeout_seconds: float = 15.0


@dataclass
class WhatsAppConfig:
    """WhatsApp 插件配置。"""

    enabled: bool = False
    auth_dir: str = ""
    dm_policy: str = "open"  # open | allowlist | disabled
    group_policy: str = "open"  # open | allowlist | disabled
    allowlist: list[str] = field(default_factory=list)
    group_allowlist: list[str] = field(default_factory=list)
    show_tool_progress: bool = False
    bridge: WhatsAppBridgeConfig = field(default_factory=WhatsAppBridgeConfig)

    @classmethod
    def from_plugin_api(cls, api: PluginApi) -> "WhatsAppConfig":
        bridge_cfg = api.get_config("bridge", {}) or {}
        return cls(
            enabled=api.get_config("enabled", False),
            auth_dir=api.get_config("auth_dir", ""),
            dm_policy=api.get_config("dm_policy", "open"),
            group_policy=api.get_config("group_policy", "open"),
            allowlist=api.get_config("allowlist", []),
            group_allowlist=api.get_config("group_allowlist", []),
            show_tool_progress=api.get_config("show_tool_progress", False),
            bridge=WhatsAppBridgeConfig(
                command=bridge_cfg.get("command", "node"),
                entry=bridge_cfg.get(
                    "entry",
                    str(Path(__file__).resolve().parent / "bridge" / "src" / "index.mjs"),
                ),
                startup_timeout_seconds=float(bridge_cfg.get("startup_timeout_seconds", 30.0)),
                send_timeout_seconds=float(bridge_cfg.get("send_timeout_seconds", 15.0)),
            ),
        )
