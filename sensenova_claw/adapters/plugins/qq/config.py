"""QQ 插件配置。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from sensenova_claw.adapters.plugins.base import PluginApi


QQMode = Literal["official", "onebot"]
QQPolicy = Literal["open", "allowlist", "disabled"]


@dataclass
class QQOfficialConfig:
    """QQ 官方开放平台配置。"""

    app_id: str = ""
    client_secret: str = ""
    sandbox: bool = False
    intents: list[str] = field(default_factory=list)


@dataclass
class QQOneBotConfig:
    """QQ OneBot/NapCat 配置。"""

    ws_url: str = ""
    access_token: str = ""
    api_base_url: str = ""
    self_id: str = ""


@dataclass
class QQConfig:
    """QQ 插件统一配置。"""

    enabled: bool = False
    mode: QQMode = "onebot"
    dm_policy: QQPolicy = "open"
    group_policy: QQPolicy = "open"
    allowlist: list[str] = field(default_factory=list)
    group_allowlist: list[str] = field(default_factory=list)
    require_mention: bool = True
    show_tool_progress: bool = False
    reply_to_message: bool = True
    official: QQOfficialConfig = field(default_factory=QQOfficialConfig)
    onebot: QQOneBotConfig = field(default_factory=QQOneBotConfig)

    @classmethod
    def from_plugin_api(cls, api: PluginApi) -> "QQConfig":
        return cls(
            enabled=api.get_config("enabled", False),
            mode=api.get_config("mode", "onebot"),
            dm_policy=api.get_config("dm_policy", "open"),
            group_policy=api.get_config("group_policy", "open"),
            allowlist=api.get_config("allowlist", []),
            group_allowlist=api.get_config("group_allowlist", []),
            require_mention=api.get_config("require_mention", True),
            show_tool_progress=api.get_config("show_tool_progress", False),
            reply_to_message=api.get_config("reply_to_message", True),
            official=QQOfficialConfig(
                app_id=api.get_config("official_app_id", ""),
                client_secret=api.get_config("official_client_secret", ""),
                sandbox=api.get_config("official_sandbox", False),
                intents=api.get_config("official_intents", []),
            ),
            onebot=QQOneBotConfig(
                ws_url=api.get_config("onebot_ws_url", ""),
                access_token=api.get_config("onebot_access_token", ""),
                api_base_url=api.get_config("onebot_api_base_url", ""),
                self_id=api.get_config("onebot_self_id", ""),
            ),
        )
