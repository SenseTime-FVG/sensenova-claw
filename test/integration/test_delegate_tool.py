"""A05: DelegateTool 执行 + 深度限制"""
import asyncio
import pytest
from pathlib import Path
from app.agents.config import AgentConfig
from app.agents.registry import AgentRegistry
from app.events.bus import PublicEventBus
from app.events.envelope import EventEnvelope
from app.events.router import BusRouter
from app.events.types import AGENT_STEP_COMPLETED, USER_INPUT
from app.tools.delegate_tool import DelegateTool

pytestmark = pytest.mark.asyncio


class TestDelegateTool:
    async def test_delegate_success(self, test_repo):
        bus_router = BusRouter(public_bus=PublicEventBus(), ttl_seconds=60, gc_interval=60)
        await bus_router.start()
        reg = AgentRegistry(config_dir=Path("/tmp/_agents"))
        reg.register(AgentConfig.create(id="default", name="D"))
        reg.register(AgentConfig.create(id="helper", name="H"))
        await test_repo.create_session("parent", meta={"agent_id": "default"})

        async def fake_agent():
            async for e in bus_router.public_bus.subscribe():
                if e.type == USER_INPUT and e.session_id.startswith("delegate_"):
                    await asyncio.sleep(0.05)
                    await bus_router.public_bus.publish(EventEnvelope(
                        type=AGENT_STEP_COMPLETED, session_id=e.session_id,
                        source="test", payload={"result": {"content": "done"}},
                    ))
                    return

        task = asyncio.create_task(fake_agent())
        tool = DelegateTool(agent_registry=reg, bus_router=bus_router, repo=test_repo, timeout=5)
        result = await tool.execute(target_agent="helper", task="test", _session_id="parent")
        assert result["success"] is True
        assert result["result"] == "done"
        task.cancel()
        await bus_router.stop()

    async def test_depth_limit(self, test_repo):
        bus_router = BusRouter(public_bus=PublicEventBus(), ttl_seconds=60, gc_interval=60)
        await bus_router.start()
        reg = AgentRegistry(config_dir=Path("/tmp/_agents"))
        reg.register(AgentConfig.create(id="h", name="H", max_delegation_depth=1))
        await test_repo.create_session("deep", meta={"delegation_depth": 1})
        tool = DelegateTool(agent_registry=reg, bus_router=bus_router, repo=test_repo, timeout=5)
        result = await tool.execute(target_agent="h", task="t", _session_id="deep")
        assert result["success"] is False
        assert "depth" in result["error"].lower()
        await bus_router.stop()

    async def test_target_not_found(self, test_repo):
        bus_router = BusRouter(public_bus=PublicEventBus(), ttl_seconds=60, gc_interval=60)
        await bus_router.start()
        reg = AgentRegistry(config_dir=Path("/tmp/_agents"))
        tool = DelegateTool(agent_registry=reg, bus_router=bus_router, repo=test_repo, timeout=5)
        result = await tool.execute(target_agent="nope", task="t", _session_id="s")
        assert result["success"] is False
        assert "not found" in result["error"].lower()
        await bus_router.stop()

    async def test_timeout(self, test_repo):
        bus_router = BusRouter(public_bus=PublicEventBus(), ttl_seconds=60, gc_interval=60)
        await bus_router.start()
        reg = AgentRegistry(config_dir=Path("/tmp/_agents"))
        reg.register(AgentConfig.create(id="slow", name="Slow"))
        await test_repo.create_session("timeout_s", meta={})
        tool = DelegateTool(agent_registry=reg, bus_router=bus_router, repo=test_repo, timeout=0.5)
        result = await tool.execute(target_agent="slow", task="t", _session_id="timeout_s")
        assert result["success"] is False
        assert "timed out" in result["error"].lower()
        await bus_router.stop()
