from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path

import pytest

from agentos.adapters.llm.factory import LLMFactory
from agentos.adapters.storage.repository import Repository
from agentos.capabilities.agents.registry import AgentRegistry
from agentos.capabilities.miniapps.service import MiniAppService
from agentos.capabilities.tools.registry import ToolRegistry
from agentos.interfaces.ws.gateway import Gateway
from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.persister import EventPersister
from agentos.kernel.events.router import BusRouter
from agentos.kernel.events.types import AGENT_STEP_COMPLETED
from agentos.kernel.runtime.agent_runtime import AgentRuntime
from agentos.kernel.runtime.context_builder import ContextBuilder
from agentos.kernel.runtime.llm_runtime import LLMRuntime
from agentos.kernel.runtime.publisher import EventPublisher
from agentos.kernel.runtime.state import SessionStateStore
from agentos.kernel.runtime.tool_runtime import ToolRuntime
from agentos.platform.config.config import config


@pytest.mark.asyncio
async def test_miniapp_interaction_end_to_end(tmp_path: Path) -> None:
    agentos_home = tmp_path / "agentos_home"
    db_path = tmp_path / "agentos.db"

    original_config = copy.deepcopy(config.data)
    config.data["llm"]["default_model"] = "mock"
    config.data["agents"]["default"]["model"] = "mock"
    for agent_cfg in config.data.get("agents", {}).values():
        if isinstance(agent_cfg, dict):
            agent_cfg.pop("system_prompt", None)
    config.data["system"]["agentos_home"] = str(agentos_home)
    config.data["system"]["database_path"] = str(db_path)
    config.data["system"]["log_level"] = "DEBUG"

    repo = Repository(db_path=str(db_path))
    await repo.init()

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    persister = EventPersister(bus=bus, repo=repo)
    bus_router = BusRouter(public_bus=bus, ttl_seconds=3600, gc_interval=60)

    tool_registry = ToolRegistry()
    state_store = SessionStateStore()
    agent_registry = AgentRegistry(agentos_home=agentos_home)
    agent_registry.load_from_config(config.data)
    context_builder = ContextBuilder(tool_registry=tool_registry, agentos_home=str(agentos_home))
    context_builder.agent_registry = agent_registry

    agent_runtime = AgentRuntime(
        bus_router=bus_router,
        repo=repo,
        context_builder=context_builder,
        tool_registry=tool_registry,
        state_store=state_store,
        agent_registry=agent_registry,
    )
    llm_runtime = LLMRuntime(bus_router=bus_router, factory=LLMFactory())
    tool_runtime = ToolRuntime(bus_router=bus_router, registry=tool_registry, agent_registry=agent_registry)

    gateway = Gateway(publisher=publisher, repo=repo, agent_registry=agent_registry)
    miniapp_service = MiniAppService(
        agentos_home=agentos_home,
        config=config,
        agent_registry=agent_registry,
        gateway=gateway,
    )

    await persister.start()
    await bus_router.start()
    await agent_runtime.start()
    await llm_runtime.start()
    await tool_runtime.start()
    await asyncio.sleep(0.1)

    collected: list[EventEnvelope] = []
    target_session_id: str | None = None
    done_event = asyncio.Event()

    async def collector() -> None:
        async for event in bus.subscribe():
            collected.append(event)
            if target_session_id and event.session_id == target_session_id and event.type == AGENT_STEP_COMPLETED:
                done_event.set()
                break

    collect_task = asyncio.create_task(collector())
    await asyncio.sleep(0.05)

    try:
        page = await miniapp_service.create_page(
            {
                "name": "研究工作台",
                "description": "根据用户完成情况继续规划下一轮任务",
                "agent_id": "default",
                "create_dedicated_agent": True,
                "workspace_mode": "scratch",
                "builder_type": "builtin",
                "generation_prompt": "做一个通用 workspace，页面结构固定，内容按需要迭代",
            }
        )

        interaction = await miniapp_service.dispatch_interaction(
            page["slug"],
            action="workspace_result_submitted",
            payload={"completed_cards": 3, "summary": "用户完成了本轮任务"},
        )
        target_session_id = interaction["session_id"]

        await asyncio.wait_for(done_event.wait(), timeout=10)

        session_events = [event.type for event in collected if event.session_id == target_session_id]
        assert "user.input" in session_events
        assert "agent.step_started" in session_events
        assert "llm.call_requested" in session_events
        assert "llm.call_completed" in session_events
        assert "agent.step_completed" in session_events

        history = await repo.get_session_events(target_session_id)
        assert history
        joined = "\n".join(str(item.get("payload_json")) for item in history)
        payloads = [json.loads(item["payload_json"]) for item in history if item.get("payload_json")]
        assert "MiniApp 交互事件" in joined
        assert any("workspace_result_submitted" in json.dumps(item, ensure_ascii=False) for item in payloads)
    finally:
        collect_task.cancel()
        await agent_runtime.stop()
        await llm_runtime.stop()
        await tool_runtime.stop()
        await bus_router.stop()
        await persister.stop()
        config.data = original_config
