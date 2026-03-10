from __future__ import annotations

import asyncio
import sqlite3
import uuid
from pathlib import Path

import pytest

from app.core.config import config
from app.core.logging import setup_logging
from app.db.repository import Repository
from app.events.bus import PublicEventBus
from app.events.envelope import EventEnvelope
from app.events.persister import EventPersister
from app.events.router import BusRouter
from app.events.types import AGENT_STEP_COMPLETED, USER_INPUT
from app.llm.factory import LLMFactory
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.context_builder import ContextBuilder
from app.runtime.llm_runtime import LLMRuntime
from app.runtime.publisher import EventPublisher
from app.runtime.state import SessionStateStore
from app.runtime.tool_runtime import ToolRuntime
from app.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_backend_e2e_event_flow(tmp_path: Path):
    db_path = tmp_path / "agentos.db"
    workspace = tmp_path / "workspace"

    config.data["agent"]["provider"] = "mock"
    config.data["agent"]["default_model"] = "mock-agent-v1"
    config.data["agent"]["default_temperature"] = 0.2
    config.data["system"]["database_path"] = str(db_path)
    config.data["system"]["workspace_dir"] = str(workspace)
    config.data["system"]["log_level"] = "DEBUG"
    config.data["tools"]["serper_search"]["api_key"] = ""

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

    await persister.start()
    await bus_router.start()
    await agent_runtime.start()
    await llm_runtime.start()
    await tool_runtime.start()
    await asyncio.sleep(0.1)

    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    turn_id = f"turn_{uuid.uuid4().hex[:12]}"
    query = "你好"

    collected: list[EventEnvelope] = []
    done_event = asyncio.Event()

    async def collector() -> None:
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
        await publisher.publish(
            EventEnvelope(
                type=USER_INPUT,
                session_id=session_id,
                turn_id=turn_id,
                source="ui",
                payload={"content": query, "attachments": [], "context_files": []},
            )
        )

        await asyncio.wait_for(done_event.wait(), timeout=10)
    finally:
        collect_task.cancel()
        await agent_runtime.stop()
        await llm_runtime.stop()
        await tool_runtime.stop()
        await bus_router.stop()
        await persister.stop()

    event_types = [event.type for event in collected]
    assert "agent.step_started" in event_types
    assert "llm.call_requested" in event_types
    assert "llm.call_completed" in event_types
    assert "agent.step_completed" in event_types

    # 验证数据库持久化
    assert db_path.exists()
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(1) FROM events WHERE session_id = ?", (session_id,)).fetchone()[0]
    conn.close()
    assert count >= 4
