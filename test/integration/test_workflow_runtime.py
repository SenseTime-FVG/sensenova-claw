"""W03: WorkflowRuntime DAG 调度（简化集成测试）"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
from app.workflows.models import Workflow, WorkflowNode, WorkflowEdge
from app.workflows.registry import WorkflowRegistry
from app.agents.config import AgentConfig
from app.agents.registry import AgentRegistry
from app.events.bus import PublicEventBus
from app.events.envelope import EventEnvelope
from app.events.router import BusRouter
from app.events.types import AGENT_STEP_COMPLETED, USER_INPUT
from app.runtime.publisher import EventPublisher

pytestmark = pytest.mark.asyncio


class TestWorkflowRuntime:
    async def test_simple_linear_workflow(self, test_repo):
        from app.workflows.runtime import WorkflowRuntime

        bus = PublicEventBus()
        bus_router = BusRouter(public_bus=bus, ttl_seconds=60, gc_interval=60)
        await bus_router.start()

        publisher = EventPublisher(bus=bus)
        agent_reg = AgentRegistry(config_dir=Path("/tmp/_wr_agents"))
        agent_reg.register(AgentConfig.create(id="default", name="D"))

        wf_reg = WorkflowRegistry(config_dir=Path("/tmp/_wr_wf"))
        wf = Workflow(
            id="linear", name="Linear",
            nodes=[WorkflowNode(id="n1", input_template="{workflow.input}")],
            edges=[], entry_node="n1", exit_nodes=["n1"],
        )
        wf_reg.register(wf)

        runtime = WorkflowRuntime(
            agent_registry=agent_reg,
            workflow_registry=wf_reg,
            bus_router=bus_router,
            repo=test_repo,
            publisher=publisher,
        )

        # fake agent 响应
        async def fake_agent():
            async for e in bus.subscribe():
                if e.type == USER_INPUT and e.session_id.startswith("wf_"):
                    await asyncio.sleep(0.05)
                    await bus.publish(EventEnvelope(
                        type=AGENT_STEP_COMPLETED, session_id=e.session_id,
                        source="test", payload={"result": {"content": "output from n1"}},
                    ))
                    return

        task = asyncio.create_task(fake_agent())
        run = await runtime.execute("linear", "test input", "wf_test_sess")

        assert run.status == "completed"
        assert "output from n1" in run.output
        task.cancel()
        await bus_router.stop()

    async def test_workflow_not_found(self, test_repo):
        from app.workflows.runtime import WorkflowRuntime

        bus = PublicEventBus()
        publisher = EventPublisher(bus=bus)
        bus_router = BusRouter(public_bus=bus, ttl_seconds=60, gc_interval=60)
        agent_reg = AgentRegistry(config_dir=Path("/tmp/_wr_agents"))
        wf_reg = WorkflowRegistry(config_dir=Path("/tmp/_wr_wf"))

        runtime = WorkflowRuntime(
            agent_registry=agent_reg,
            workflow_registry=wf_reg,
            bus_router=bus_router,
            repo=test_repo,
            publisher=publisher,
        )

        with pytest.raises(ValueError, match="not found"):
            await runtime.execute("nope", "input", "sess")
