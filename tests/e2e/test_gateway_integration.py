from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest

from agentos.platform.config.config import config
from agentos.platform.logging.setup import setup_logging
from agentos.adapters.storage.repository import Repository
from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.persister import EventPersister
from agentos.kernel.events.router import BusRouter
from agentos.kernel.events.types import AGENT_STEP_COMPLETED, USER_INPUT
from agentos.adapters.channels.websocket_channel import WebSocketChannel
from agentos.interfaces.ws.gateway import Gateway
from agentos.adapters.llm.factory import LLMFactory
from agentos.kernel.runtime.agent_runtime import AgentRuntime
from agentos.kernel.runtime.context_builder import ContextBuilder
from agentos.kernel.runtime.llm_runtime import LLMRuntime
from agentos.kernel.runtime.publisher import EventPublisher
from agentos.kernel.runtime.state import SessionStateStore
from agentos.kernel.runtime.tool_runtime import ToolRuntime
from agentos.capabilities.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_gateway_with_websocket_channel(tmp_path: Path):
    """测试 Gateway 与 WebSocketChannel 集成（双总线架构）"""
    db_path = tmp_path / "agentos.db"
    workspace = tmp_path / "workspace"

    config.data["agent"]["provider"] = "mock"
    config.data["agent"]["default_model"] = "mock-agent-v1"
    config.data["system"]["database_path"] = str(db_path)
    config.data["system"]["workspace_dir"] = str(workspace)

    setup_logging()

    repo = Repository()
    await repo.init()

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    persister = EventPersister(bus=bus, repo=repo)
    bus_router = BusRouter(public_bus=bus, ttl_seconds=3600, gc_interval=60)

    tool_registry = ToolRegistry()
    state_store = SessionStateStore()
    context_builder = ContextBuilder(tool_registry=tool_registry)

    agent_runtime = AgentRuntime(
        bus_router=bus_router,
        repo=repo,
        context_builder=context_builder,
        tool_registry=tool_registry,
        state_store=state_store,
    )
    llm_runtime = LLMRuntime(bus_router=bus_router, factory=LLMFactory())
    tool_runtime = ToolRuntime(bus_router=bus_router, registry=tool_registry)

    gateway = Gateway(publisher=publisher)
    ws_channel = WebSocketChannel("websocket")
    gateway.register_channel(ws_channel)

    await persister.start()
    await bus_router.start()
    await agent_runtime.start()
    await llm_runtime.start()
    await tool_runtime.start()
    await gateway.start()
    await asyncio.sleep(0.1)

    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    turn_id = f"turn_{uuid.uuid4().hex[:12]}"
    query = "测试查询"

    gateway.bind_session(session_id, "websocket")

    collected: list[EventEnvelope] = []
    done_event = asyncio.Event()

    async def collector():
        async for event in bus.subscribe():
            if event.session_id != session_id:
                continue
            collected.append(event)
            if event.type == AGENT_STEP_COMPLETED:
                done_event.set()
                break

    collect_task = asyncio.create_task(collector())
    await asyncio.sleep(0.1)

    try:
        event = EventEnvelope(
            type=USER_INPUT,
            session_id=session_id,
            turn_id=turn_id,
            source="websocket",
            payload={"content": query, "attachments": [], "context_files": []},
        )
        await gateway.publish_from_channel(event)

        await asyncio.wait_for(done_event.wait(), timeout=10)
    finally:
        collect_task.cancel()
        await gateway.stop()
        await agent_runtime.stop()
        await llm_runtime.stop()
        await tool_runtime.stop()
        await bus_router.stop()
        await persister.stop()

    event_types = [event.type for event in collected]
    assert "agent.step_started" in event_types
    assert "agent.step_completed" in event_types
