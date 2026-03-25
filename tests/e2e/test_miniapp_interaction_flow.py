from __future__ import annotations

import asyncio
import copy
import json
import os
from pathlib import Path

import pytest

from sensenova_claw.adapters.llm.factory import LLMFactory
from sensenova_claw.adapters.storage.repository import Repository
from sensenova_claw.capabilities.agents.registry import AgentRegistry
from sensenova_claw.capabilities.miniapps.service import MiniAppService
from sensenova_claw.capabilities.tools.registry import ToolRegistry
from sensenova_claw.interfaces.ws.gateway import Gateway
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.persister import EventPersister
from sensenova_claw.kernel.events.router import BusRouter
from sensenova_claw.kernel.events.types import AGENT_STEP_COMPLETED
from sensenova_claw.kernel.runtime.agent_runtime import AgentRuntime
from sensenova_claw.kernel.runtime.context_builder import ContextBuilder
from sensenova_claw.kernel.runtime.llm_runtime import LLMRuntime
from sensenova_claw.kernel.runtime.publisher import EventPublisher
from sensenova_claw.kernel.runtime.state import SessionStateStore
from sensenova_claw.kernel.runtime.tool_runtime import ToolRuntime
from sensenova_claw.platform.config.config import config


@pytest.mark.asyncio
async def test_miniapp_interaction_end_to_end(tmp_path: Path) -> None:
    sensenova_claw_home = tmp_path / "sensenova_claw_home"
    db_path = tmp_path / "sensenova-claw.db"

    original_config = copy.deepcopy(config.data)
    previous_home = os.environ.get("SENSENOVA_CLAW_HOME")
    os.environ["SENSENOVA_CLAW_HOME"] = str(sensenova_claw_home)
    config.data["llm"]["default_model"] = "mock"
    config.data["agents"]["default"]["model"] = "mock"
    for agent_cfg in config.data.get("agents", {}).values():
        if isinstance(agent_cfg, dict):
            agent_cfg.pop("system_prompt", None)
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
    agent_registry = AgentRegistry(sensenova_claw_home=sensenova_claw_home)
    agent_registry.load_from_config(config.data)
    context_builder = ContextBuilder(tool_registry=tool_registry, sensenova_claw_home=str(sensenova_claw_home))
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
        sensenova_claw_home=sensenova_claw_home,
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
        if previous_home is None:
            os.environ.pop("SENSENOVA_CLAW_HOME", None)
        else:
            os.environ["SENSENOVA_CLAW_HOME"] = previous_home
