"""ConfigManager 的 secret-aware 写入单测"""
import pytest
import yaml

from agentos.kernel.events.bus import PublicEventBus
from agentos.platform.config.config import Config
from agentos.platform.config.config_manager import ConfigManager
from agentos.platform.secrets.store import InMemorySecretStore


@pytest.mark.asyncio
async def test_update_writes_secret_ref_for_sensitive_path(tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text("tools: {}\n", encoding="utf-8")
    store = InMemorySecretStore()
    cfg = Config(config_path=config_path, secret_store=store)
    bus = PublicEventBus()
    manager = ConfigManager(config=cfg, event_bus=bus, secret_store=store)

    await manager.update("tools", {"serper_search": {"api_key": "sk-secret-123"}})

    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["tools"]["serper_search"]["api_key"] == (
        "${secret:agentos/tools.serper_search.api_key}"
    )
    assert store.get("agentos/tools.serper_search.api_key") == "sk-secret-123"


@pytest.mark.asyncio
async def test_update_writes_plain_value_for_non_secret_path(tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text("agent: {}\n", encoding="utf-8")
    store = InMemorySecretStore()
    cfg = Config(config_path=config_path, secret_store=store)
    bus = PublicEventBus()
    manager = ConfigManager(config=cfg, event_bus=bus, secret_store=store)

    await manager.update("agent", {"model": "gpt-5.4"})

    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["agent"]["model"] == "gpt-5.4"


@pytest.mark.asyncio
async def test_update_deletes_secret_when_value_is_empty(tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "tools:\n  serper_search:\n    api_key: ${secret:agentos/tools.serper_search.api_key}\n",
        encoding="utf-8",
    )
    store = InMemorySecretStore()
    store.set("agentos/tools.serper_search.api_key", "sk-old")
    cfg = Config(config_path=config_path, secret_store=store)
    bus = PublicEventBus()
    manager = ConfigManager(config=cfg, event_bus=bus, secret_store=store)

    await manager.update("tools", {"serper_search": {"api_key": ""}})

    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["tools"]["serper_search"]["api_key"] == ""
    assert store.get("agentos/tools.serper_search.api_key") is None
