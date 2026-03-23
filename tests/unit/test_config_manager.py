"""ConfigManager 单元测试"""
import asyncio
import pytest
import yaml
from pathlib import Path

from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.events.types import CONFIG_UPDATED, SYSTEM_SESSION_ID
from agentos.platform.config.config_manager import ConfigManager
from agentos.platform.config.config import Config
from agentos.platform.secrets.store import InMemorySecretStore


@pytest.fixture
def setup(tmp_path):
    config_path = tmp_path / "config.yml"
    initial = {
        "llm": {
            "providers": {"openai": {"api_key": "sk-old", "base_url": ""}},
            "default_model": "gpt-4o-mini",
        },
        "agent": {"temperature": 0.2},
        "tools": {},
    }
    config_path.write_text(yaml.dump(initial), encoding="utf-8")
    secret_store = InMemorySecretStore()
    cfg = Config(config_path=config_path, secret_store=secret_store)
    bus = PublicEventBus()
    manager = ConfigManager(config=cfg, event_bus=bus, secret_store=secret_store)
    return manager, cfg, bus, config_path, secret_store


@pytest.mark.asyncio
async def test_update_persists_to_yaml(setup):
    manager, cfg, bus, config_path, _ = setup
    await manager.update("agent", {"temperature": 0.8})
    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["agent"]["temperature"] == 0.8


@pytest.mark.asyncio
async def test_update_refreshes_memory(setup):
    manager, cfg, bus, config_path, _ = setup
    await manager.update("agent", {"temperature": 0.9})
    assert cfg.data["agent"]["temperature"] == 0.9


@pytest.mark.asyncio
async def test_update_publishes_event(setup):
    manager, cfg, bus, config_path, _ = setup
    events = []
    async def collect():
        async for event in bus.subscribe():
            events.append(event)
    task = asyncio.create_task(collect())
    await asyncio.sleep(0)
    await manager.update("agent", {"temperature": 0.7})
    await asyncio.sleep(0.05)
    task.cancel()
    assert len(events) == 1
    assert events[0].type == CONFIG_UPDATED
    assert events[0].session_id == SYSTEM_SESSION_ID
    assert events[0].payload["section"] == "agent"
    assert "agent.temperature" in events[0].payload["changes"]
    assert events[0].payload["changes"]["agent.temperature"]["new"] == 0.7


@pytest.mark.asyncio
async def test_update_deep_merges(setup):
    manager, cfg, bus, config_path, _ = setup
    await manager.update("llm", {"providers": {"anthropic": {"api_key": "sk-ant"}}})
    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert "openai" in written["llm"]["providers"]
    assert "anthropic" in written["llm"]["providers"]


@pytest.mark.asyncio
async def test_update_handles_secrets(setup):
    manager, cfg, bus, config_path, secret_store = setup
    await manager.update("llm", {"providers": {"openai": {"api_key": "sk-new"}}})
    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["llm"]["providers"]["openai"]["api_key"].startswith("${secret:")
    assert secret_store.get("agentos/llm.providers.openai.api_key") == "sk-new"


@pytest.mark.asyncio
async def test_update_event_masks_secrets(setup):
    manager, cfg, bus, config_path, _ = setup
    events = []
    async def collect():
        async for event in bus.subscribe():
            events.append(event)
    task = asyncio.create_task(collect())
    await asyncio.sleep(0)
    await manager.update("llm", {"providers": {"openai": {"api_key": "sk-newsecretkey"}}})
    await asyncio.sleep(0.05)
    task.cancel()
    changes = events[0].payload["changes"]
    api_key_change = changes.get("llm.providers.openai.api_key", {})
    assert "sk-newsecretkey" not in str(api_key_change)


@pytest.mark.asyncio
async def test_update_preserves_other_sections(setup):
    manager, cfg, bus, config_path, _ = setup
    await manager.update("agent", {"temperature": 0.5})
    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert "llm" in written
    assert "tools" in written


@pytest.mark.asyncio
async def test_update_concurrent_lock(setup):
    manager, cfg, bus, config_path, _ = setup
    async def update_agent(temp):
        await manager.update("agent", {"temperature": temp})
    await asyncio.gather(update_agent(0.1), update_agent(0.2), update_agent(0.3))
    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["agent"]["temperature"] in (0.1, 0.2, 0.3)
    assert "llm" in written


@pytest.mark.asyncio
async def test_get_section(setup):
    manager, cfg, bus, config_path, _ = setup
    result = manager.get_section("llm")
    assert "providers" in result


@pytest.mark.asyncio
async def test_update_new_section(setup):
    manager, cfg, bus, config_path, _ = setup
    await manager.update("memory", {"enabled": True})
    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["memory"]["enabled"] is True


@pytest.mark.asyncio
async def test_update_empty_data_no_event(setup):
    manager, cfg, bus, config_path, _ = setup
    events = []
    async def collect():
        async for event in bus.subscribe():
            events.append(event)
    task = asyncio.create_task(collect())
    await asyncio.sleep(0)
    await manager.update("agent", {})
    await asyncio.sleep(0.05)
    task.cancel()
    assert len(events) == 0
