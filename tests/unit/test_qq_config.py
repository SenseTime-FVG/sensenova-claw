"""QQ 插件配置单元测试。"""

from __future__ import annotations

from sensenova_claw.adapters.plugins import PluginRegistry
from sensenova_claw.adapters.plugins.base import PluginApi
from sensenova_claw.adapters.plugins.qq.config import QQConfig
from sensenova_claw.interfaces.ws.gateway import Gateway
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.runtime.publisher import EventPublisher


def _make_plugin_api(config_overrides: dict | None = None) -> PluginApi:
    from sensenova_claw.platform.config.config import config as global_config

    defaults = {
        "enabled": True,
        "mode": "onebot",
        "dm_policy": "open",
        "group_policy": "open",
        "allowlist": [],
        "group_allowlist": [],
        "require_mention": True,
        "show_tool_progress": False,
        "reply_to_message": True,
        "official_app_id": "",
        "official_client_secret": "",
        "official_public_key": "",
        "official_sandbox": False,
        "official_webhook_secret": "",
        "official_intents": [],
        "onebot_ws_url": "ws://127.0.0.1:3001",
        "onebot_access_token": "",
        "onebot_api_base_url": "http://127.0.0.1:3000",
        "onebot_self_id": "",
    }
    if config_overrides:
        defaults.update(config_overrides)

    for key, value in defaults.items():
        global_config.set(f"plugins.qq.{key}", value)

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)
    registry = PluginRegistry()
    registry._gateway = gateway
    registry._publisher = publisher
    return PluginApi(plugin_id="qq", registry=registry)


def test_from_plugin_api_parses_onebot_mode() -> None:
    api = _make_plugin_api(
        {
            "mode": "onebot",
            "group_policy": "allowlist",
            "group_allowlist": ["10001"],
            "onebot_access_token": "abc",
            "onebot_self_id": "424242",
        }
    )

    cfg = QQConfig.from_plugin_api(api)

    assert cfg.mode == "onebot"
    assert cfg.group_policy == "allowlist"
    assert cfg.group_allowlist == ["10001"]
    assert cfg.onebot.access_token == "abc"
    assert cfg.onebot.self_id == "424242"


def test_from_plugin_api_parses_official_mode() -> None:
    api = _make_plugin_api(
        {
            "mode": "official",
            "official_app_id": "app-1",
            "official_client_secret": "secret-1",
            "official_public_key": "pub-1",
            "official_sandbox": True,
            "official_webhook_secret": "hook-1",
            "official_intents": ["PUBLIC_GUILD_MESSAGES"],
        }
    )

    cfg = QQConfig.from_plugin_api(api)

    assert cfg.mode == "official"
    assert cfg.official.app_id == "app-1"
    assert cfg.official.client_secret == "secret-1"
    assert cfg.official.public_key == "pub-1"
    assert cfg.official.sandbox is True
    assert cfg.official.webhook_secret == "hook-1"
    assert cfg.official.intents == ["PUBLIC_GUILD_MESSAGES"]
