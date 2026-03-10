"""飞书插件配置"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.plugins.base import PluginApi


@dataclass
class FeishuConfig:
    """飞书插件配置"""

    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""
    dm_policy: str = "open"  # open | allowlist
    group_policy: str = "mention"  # mention | open | disabled
    allowlist: list[str] = field(default_factory=list)
    log_level: str = "INFO"

    @classmethod
    def from_plugin_api(cls, api: PluginApi) -> FeishuConfig:
        return cls(
            enabled=api.get_config("enabled", False),
            app_id=api.get_config("app_id", ""),
            app_secret=api.get_config("app_secret", ""),
            dm_policy=api.get_config("dm_policy", "open"),
            group_policy=api.get_config("group_policy", "mention"),
            allowlist=api.get_config("allowlist", []),
            log_level=api.get_config("log_level", "INFO"),
        )
