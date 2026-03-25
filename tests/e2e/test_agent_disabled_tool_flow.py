from __future__ import annotations

import asyncio
import copy
from pathlib import Path

import pytest

from sensenova_claw.adapters.llm.factory import LLMFactory
from sensenova_claw.adapters.storage.repository import Repository
from sensenova_claw.capabilities.agents.config import AgentConfig
from sensenova_claw.capabilities.agents.registry import AgentRegistry
from sensenova_claw.capabilities.tools.base import Tool
from sensenova_claw.capabilities.tools.registry import ToolRegistry
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.router import BusRouter
from sensenova_claw.kernel.events.types import (
    LLM_CALL_REQUESTED,
    TOOL_CALL_RESULT,
    USER_INPUT,
)
from sensenova_claw.kernel.runtime.agent_runtime import AgentRuntime
from sensenova_claw.kernel.runtime.context_builder import ContextBuilder
from sensenova_claw.kernel.runtime.llm_runtime import LLMRuntime
from sensenova_claw.kernel.runtime.state import SessionStateStore
from sensenova_claw.kernel.runtime.tool_runtime import ToolRuntime
from sensenova_claw.platform.config.config import config


class _FlagSerperTool(Tool):
    name = "serper_search"
    description = "测试搜索工具"
    parameters = {"type": "object", "properties": {}}

    def __init__(self):
        self.executed = False

    async def execute(self, **kwargs):
        _ = kwargs
        self.executed = True
        return {"items": []}


@pytest.mark.asyncio
async def test_disabled_tool_is_not_exposed_or_executed_in_agent_chat_flow(tmp_path: Path):
    """Agent 聊天链路里，禁用工具后既不应暴露给 LLM，也不应被真正执行。"""
    original_config = copy.deepcopy(config.data)
    config.data["agent"]["model"] = "mock"
    config.data["llm"]["default_model"] = "mock"
    config.data["system"]["sensenova_claw_home"] = str(tmp_path)

    (tmp_path / ".agent_preferences.json").write_text(
        '{"agent_tools": {"default": {"serper_search": false}}}',
        encoding="utf-8",
    )

    repo = Repository(db_path=str(tmp_path / "test.db"))
    await repo.init()

    bus = PublicEventBus()
    bus_router = BusRouter(public_bus=bus, ttl_seconds=3600, gc_interval=60)
    tool_registry = ToolRegistry()
    fake_tool = _FlagSerperTool()
    tool_registry.register(fake_tool)
    context_builder = ContextBuilder(tool_registry=tool_registry, sensenova_claw_home=str(tmp_path))
    agent_registry = AgentRegistry(sensenova_claw_home=tmp_path)
    agent_registry.register(AgentConfig.create(id="default", name="Default Agent", model="mock"))

    agent_runtime = AgentRuntime(
        bus_router=bus_router,
        repo=repo,
        context_builder=context_builder,
        tool_registry=tool_registry,
        state_store=SessionStateStore(),
        agent_registry=agent_registry,
    )
    llm_runtime = LLMRuntime(bus_router=bus_router, factory=LLMFactory())
    tool_runtime = ToolRuntime(
        bus_router=bus_router,
        registry=tool_registry,
        agent_registry=agent_registry,
    )

    await bus_router.start()
    await agent_runtime.start()
    await llm_runtime.start()
    await tool_runtime.start()

    session_id = "sess_disabled_tool"
    await repo.create_session(session_id, meta={"agent_id": "default"})

    collected: list[EventEnvelope] = []
    done = asyncio.Event()
    seen_llm_requested = False
    seen_tool_result = False

    async def collector():
        nonlocal seen_llm_requested, seen_tool_result
        async for event in bus.subscribe():
            if event.session_id != session_id:
                continue
            collected.append(event)
            if event.type == LLM_CALL_REQUESTED:
                seen_llm_requested = True
            if event.type == TOOL_CALL_RESULT:
                seen_tool_result = True
            if seen_llm_requested and seen_tool_result:
                done.set()
                return

    collector_task = asyncio.create_task(collector())
    await asyncio.sleep(0.05)

    try:
        await bus.publish(
            EventEnvelope(
                type=USER_INPUT,
                session_id=session_id,
                turn_id="turn_disabled_tool",
                source="ui",
                payload={"content": "帮我搜索英超联赛最近3年的冠亚军分别是什么球队"},
            )
        )
        await asyncio.wait_for(done.wait(), timeout=10)
    finally:
        collector_task.cancel()
        await agent_runtime.stop()
        await llm_runtime.stop()
        await tool_runtime.stop()
        await bus_router.stop()
        config.data = original_config

    llm_requested = next(event for event in collected if event.type == LLM_CALL_REQUESTED)
    tool_names = [tool["name"] for tool in llm_requested.payload.get("tools", [])]
    assert "serper_search" not in tool_names

    tool_result = next(event for event in collected if event.type == TOOL_CALL_RESULT)
    assert tool_result.payload["success"] is False
    assert "工具已被当前 Agent 禁用" in str(tool_result.payload["result"])
    assert fake_tool.executed is False
