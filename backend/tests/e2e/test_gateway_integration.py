from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest

from app.core.config import config
from app.core.logging import setup_logging
from app.db.repository import Repository
from app.events.bus import PublicEventBus
from app.events.envelope import EventEnvelope
from app.events.types import AGENT_STEP_COMPLETED, UI_USER_INPUT
from app.gateway.channels.websocket_channel import WebSocketChannel
from app.gateway.gateway import Gateway
from app.llm.factory import LLMFactory
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.context_builder import ContextBuilder
from app.runtime.llm_runtime import LLMRuntime
from app.runtime.publisher import EventPublisher
from app.runtime.state import SessionStateStore
from app.runtime.tool_runtime import ToolRuntime
from app.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_gateway_with_websocket_channel(tmp_path: Path):
    """测试 Gateway 与 WebSocketChannel 集成"""
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
    publisher = EventPublisher(bus=bus, repo=repo)

    tool_registry = ToolRegistry()
    state_store = SessionStateStore()
    context_builder = ContextBuilder()

    agent_runtime = AgentRuntime(
        publisher=publisher,
        repo=repo,
        context_builder=context_builder,
        tool_registry=tool_registry,
        state_store=state_store,
    )
    llm_runtime = LLMRuntime(publisher=publisher, factory=LLMFactory())
    tool_runtime = ToolRuntime(publisher=publisher, registry=tool_registry)

    gateway = Gateway(publisher=publisher)
    ws_channel = WebSocketChannel("websocket")
    gateway.register_channel(ws_channel)

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
            type=UI_USER_INPUT,
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

    event_types = [event.type for event in collected]
    assert "agent.step_started" in event_types
    assert "agent.step_completed" in event_types
