from __future__ import annotations

from pathlib import Path

import pytest

from sensenova_claw.capabilities.agents.registry import AgentRegistry
from sensenova_claw.capabilities.tools.base import Tool, ToolRiskLevel
from sensenova_claw.capabilities.tools.registry import ToolRegistry
from sensenova_claw.kernel.events.bus import PrivateEventBus, PublicEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.router import BusRouter
from sensenova_claw.kernel.events.types import TOOL_CALL_REQUESTED
from sensenova_claw.kernel.runtime.state import SessionStateStore
from sensenova_claw.kernel.runtime.tool_runtime import ToolRuntime
from sensenova_claw.kernel.runtime.workers.tool_worker import ToolSessionWorker
from sensenova_claw.platform.config.config import Config


class _TrackingTool(Tool):
    name = "tracking_tool"
    description = "测试用工具"
    parameters = {"type": "object", "properties": {}}
    risk_level = ToolRiskLevel.LOW

    def __init__(self):
        self.executed = False

    async def execute(self, **kwargs):
        self.executed = True
        return {"success": True, "kwargs": kwargs}


def _make_worker(session_id: str, tmp_path: Path):
    config_path = tmp_path / "config.yml"
    config_path.write_text("", encoding="utf-8")
    cfg = Config(config_path=config_path)
    cfg.set("tools.permission.enabled", False)

    public = PublicEventBus()
    private = PrivateEventBus(session_id=session_id, public_bus=public)
    registry = ToolRegistry()
    state_store = SessionStateStore()
    bus_router = BusRouter(public_bus=public)

    agent_config_dir = tmp_path / "agents"
    agent_config_dir.mkdir(exist_ok=True)
    agent_registry = AgentRegistry()
    agent_registry.load_from_config(cfg.data)

    runtime = ToolRuntime(
        bus_router=bus_router,
        registry=registry,
        agent_registry=agent_registry,
        state_store=state_store,
    )
    worker = ToolSessionWorker(session_id=session_id, private_bus=private, runtime=runtime)
    return worker, cfg


@pytest.mark.asyncio
async def test_cancelled_turn_skips_tool_execution_and_started_event(tmp_path):
    worker, cfg = _make_worker(session_id="test_cancelled", tmp_path=tmp_path)
    tool = _TrackingTool()
    worker.rt.registry.register(tool)
    worker.rt.state_store.mark_turn_cancelled("test_cancelled", "turn_1")

    event = EventEnvelope(
        type=TOOL_CALL_REQUESTED,
        session_id="test_cancelled",
        turn_id="turn_1",
        source="agent",
        payload={
            "tool_call_id": "tc_cancelled",
            "tool_name": "tracking_tool",
            "arguments": {},
        },
    )

    published: list[EventEnvelope] = []
    original_publish = worker.bus.publish

    async def capture_publish(evt: EventEnvelope):
        published.append(evt)
        await original_publish(evt)

    worker.bus.publish = capture_publish

    import sensenova_claw.kernel.runtime.workers.tool_worker as tw

    original_config = tw.config
    try:
        tw.config = cfg
        await worker._handle_tool_requested(event)
    finally:
        tw.config = original_config

    assert tool.executed is False
    assert published == []
