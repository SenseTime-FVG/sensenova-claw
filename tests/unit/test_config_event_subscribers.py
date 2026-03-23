"""config.updated 事件常量和订阅者测试"""
import pytest
from sensenova_claw.kernel.events.types import CONFIG_UPDATED, SYSTEM_SESSION_ID


def test_config_updated_constant():
    assert CONFIG_UPDATED == "config.updated"


def test_system_session_id_constant():
    assert SYSTEM_SESSION_ID == "__system__"


import asyncio
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.router import BusRouter


@pytest.mark.asyncio
async def test_bus_router_skips_config_events():
    """config.* 事件不应路由到私有总线"""
    bus = PublicEventBus()
    router = BusRouter(public_bus=bus)

    # 创建一个私有总线
    private_bus = router.get_or_create("test-session")
    delivered = []

    async def collect():
        async for event in private_bus.subscribe():
            delivered.append(event)

    task = asyncio.create_task(collect())
    await router.start()
    # 让 collect() 协程有机会开始执行并注册队列
    await asyncio.sleep(0)

    # 发布 config.updated 事件
    await bus.publish(EventEnvelope(
        type="config.updated",
        session_id="__system__",
        source="system",
        payload={"section": "llm", "changes": {}},
    ))

    # 发布一个普通事件到 test-session
    await bus.publish(EventEnvelope(
        type="user.input",
        session_id="test-session",
        payload={"text": "hello"},
    ))

    await asyncio.sleep(0.1)
    await router.stop()
    task.cancel()

    # 只应收到 user.input，不应收到 config.updated
    types = [e.type for e in delivered]
    assert "user.input" in types
    assert "config.updated" not in types


# ── Task 5: Module subscriber tests ──────────────────────────────────────────

from sensenova_claw.adapters.llm.factory import LLMFactory
from sensenova_claw.capabilities.agents.registry import AgentRegistry


@pytest.mark.asyncio
async def test_llm_factory_reloads_on_config_event():
    bus = PublicEventBus()
    factory = LLMFactory()
    task = asyncio.create_task(factory.start_config_listener(bus))
    await asyncio.sleep(0)
    await bus.publish(EventEnvelope(
        type=CONFIG_UPDATED,
        session_id=SYSTEM_SESSION_ID,
        source="system",
        payload={"section": "llm", "changes": {}},
    ))
    await asyncio.sleep(0.1)
    task.cancel()
    assert "mock" in factory._providers


@pytest.mark.asyncio
async def test_llm_factory_ignores_non_llm_events():
    bus = PublicEventBus()
    factory = LLMFactory()
    factory._providers["test"] = factory._providers["mock"]
    task = asyncio.create_task(factory.start_config_listener(bus))
    await asyncio.sleep(0)
    await bus.publish(EventEnvelope(
        type=CONFIG_UPDATED,
        session_id=SYSTEM_SESSION_ID,
        source="system",
        payload={"section": "agent", "changes": {}},
    ))
    await asyncio.sleep(0.1)
    task.cancel()
    assert "test" in factory._providers


@pytest.mark.asyncio
async def test_agent_registry_reloads_on_config_event(tmp_path):
    import yaml
    from sensenova_claw.platform.config.config import Config

    bus = PublicEventBus()
    registry = AgentRegistry(sensenova_claw_home=tmp_path)
    config_path = tmp_path / "config.yml"
    config_path.write_text(yaml.dump({
        "agent": {"temperature": 0.2},
        "agents": {"bot1": {"name": "Bot1", "description": "test"}},
    }), encoding="utf-8")
    cfg = Config(config_path=config_path)
    registry.load_from_config(cfg.data)
    assert registry.get("bot1") is not None

    new_data = {
        "agent": {"temperature": 0.2},
        "agents": {
            "bot1": {"name": "Bot1", "description": "test"},
            "bot2": {"name": "Bot2", "description": "new bot"},
        },
    }
    config_path.write_text(yaml.dump(new_data), encoding="utf-8")
    cfg.data = cfg._load_config()

    task = asyncio.create_task(registry.start_config_listener(bus, cfg))
    await asyncio.sleep(0)
    await bus.publish(EventEnvelope(
        type=CONFIG_UPDATED,
        session_id=SYSTEM_SESSION_ID,
        source="system",
        payload={"section": "agents", "changes": {}},
    ))
    await asyncio.sleep(0.1)
    task.cancel()
    assert registry.get("bot2") is not None


@pytest.mark.asyncio
async def test_memory_manager_reloads_on_config_event(tmp_path):
    from sensenova_claw.capabilities.memory.config import MemoryConfig
    from sensenova_claw.capabilities.memory.manager import MemoryManager

    bus = PublicEventBus()
    mem_config = MemoryConfig.from_dict({"memory": {"enabled": False}})
    db_path = tmp_path / "mem.db"
    manager = MemoryManager(
        workspace_dir=str(tmp_path),
        config=mem_config,
        db_path=db_path,
    )
    assert manager.config.enabled is False

    config_data = {"memory": {"enabled": True}}
    task = asyncio.create_task(
        manager.start_config_listener(bus, lambda: config_data)
    )
    await asyncio.sleep(0)
    await bus.publish(EventEnvelope(
        type=CONFIG_UPDATED,
        session_id=SYSTEM_SESSION_ID,
        source="system",
        payload={"section": "memory", "changes": {}},
    ))
    await asyncio.sleep(0.1)
    task.cancel()
    assert manager.config.enabled is True


# ── Task 6: Gateway broadcast config.* events ────────────────────────────────

@pytest.mark.asyncio
async def test_gateway_broadcasts_config_events():
    from unittest.mock import AsyncMock, MagicMock
    from sensenova_claw.interfaces.ws.gateway import Gateway

    bus = PublicEventBus()
    publisher = MagicMock()
    publisher.bus = bus

    gateway = Gateway(publisher=publisher, repo=None, agent_registry=None)

    ch1 = MagicMock()
    ch1.send_event = AsyncMock()
    ch1.event_filter = MagicMock(return_value=None)
    ch1.start = AsyncMock()
    ch1.stop = AsyncMock()
    gateway._channels["ch1"] = ch1

    ch2 = MagicMock()
    ch2.send_event = AsyncMock()
    ch2.event_filter = MagicMock(return_value=None)
    ch2.start = AsyncMock()
    ch2.stop = AsyncMock()
    gateway._channels["ch2"] = ch2

    await gateway.start()
    await asyncio.sleep(0)  # 让 _event_loop 协程有机会订阅总线

    await bus.publish(EventEnvelope(
        type=CONFIG_UPDATED,
        session_id=SYSTEM_SESSION_ID,
        source="system",
        payload={"section": "llm", "changes": {}},
    ))
    await asyncio.sleep(0.1)
    await gateway.stop()

    ch1.send_event.assert_called_once()
    ch2.send_event.assert_called_once()
    assert ch1.send_event.call_args[0][0].type == CONFIG_UPDATED
