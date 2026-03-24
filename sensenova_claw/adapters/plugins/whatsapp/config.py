"""WhatsApp 插件配置。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sensenova_claw.adapters.plugins.base import PluginApi

from sensenova_claw.platform.config.config import PROJECT_ROOT

logger = logging.getLogger(__name__)


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
    typing_indicator: str = "composing"  # composing | none
    dm_policy: str = "open"  # open | allowlist | disabled
    group_policy: str = "open"  # open | allowlist | disabled
    allowlist: list[str] = field(default_factory=list)
    group_allowlist: list[str] = field(default_factory=list)
    show_tool_progress: bool = False
    bridge: WhatsAppBridgeConfig = field(default_factory=WhatsAppBridgeConfig)

    @classmethod
    def from_plugin_api(cls, api: PluginApi) -> "WhatsAppConfig":
        bridge_cfg = api.get_config("bridge", {}) or {}
        raw_auth_dir = api.get_config("auth_dir", "")
        auth_dir = str(Path(raw_auth_dir).expanduser().resolve()) if raw_auth_dir else ""
        bridge_entry = cls._normalize_bridge_entry(
            bridge_cfg.get(
                "entry",
                str(Path(__file__).resolve().parent / "bridge" / "src" / "index.mjs"),
            )
        )
        return cls(
            enabled=api.get_config("enabled", False),
            auth_dir=auth_dir,
            typing_indicator=api.get_config("typing_indicator", "composing"),
            dm_policy=api.get_config("dm_policy", "open"),
            group_policy=api.get_config("group_policy", "open"),
            allowlist=api.get_config("allowlist", []),
            group_allowlist=api.get_config("group_allowlist", []),
            show_tool_progress=api.get_config("show_tool_progress", False),
            bridge=WhatsAppBridgeConfig(
                command=bridge_cfg.get("command", "node"),
                entry=bridge_entry,
                startup_timeout_seconds=float(bridge_cfg.get("startup_timeout_seconds", 30.0)),
                send_timeout_seconds=float(bridge_cfg.get("send_timeout_seconds", 15.0)),
            ),
        )

    @staticmethod
    def _normalize_bridge_entry(entry: str) -> str:
        legacy_rel = Path("sensenova_claw/adapters/channels/whatsapp/bridge/src/index.mjs")
        plugin_rel = Path("sensenova_claw/adapters/plugins/whatsapp/bridge/src/index.mjs")

        if not entry:
            return entry

        raw = Path(entry).expanduser()
        candidate = raw if raw.is_absolute() else (PROJECT_ROOT / raw)
        if candidate.exists():
            return entry

        normalized = raw.as_posix()
        if normalized.endswith(legacy_rel.as_posix()):
            replacement = str(plugin_rel)
            replacement_candidate = PROJECT_ROOT / plugin_rel
            if replacement_candidate.exists():
                logger.warning(
                    "WhatsApp bridge entry uses legacy channels path, remapping to %s",
                    replacement,
                )
                return replacement

        return entry
