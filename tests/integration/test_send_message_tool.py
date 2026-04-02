"""SendMessageTool 集成测试。"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from sensenova_claw.capabilities.agents.config import AgentConfig
from sensenova_claw.capabilities.agents.registry import AgentRegistry
from sensenova_claw.capabilities.tools.registry import ToolRegistry
from sensenova_claw.capabilities.tools.send_message_tool import SendMessageTool
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.router import BusRouter
from sensenova_claw.kernel.events.types import (
    AGENT_MESSAGE_COMPLETED,
    AGENT_STEP_COMPLETED,
    ERROR_RAISED,
    USER_INPUT,
    USER_QUESTION_ANSWERED,
    USER_QUESTION_ASKED,
    USER_TURN_CANCEL_REQUESTED,
)
from sensenova_claw.kernel.runtime.agent_message_coordinator import AgentMessageCoordinator
from sensenova_claw.kernel.runtime.agent_runtime import AgentRuntime
from sensenova_claw.kernel.runtime.context_builder import ContextBuilder
from sensenova_claw.kernel.runtime.state import SessionStateStore

pytestmark = pytest.mark.asyncio


async def _build_runtime(repo, tmp_path):
    bus = PublicEventBus()
    bus_router = BusRouter(public_bus=bus, ttl_seconds=60, gc_interval=60)
    registry = AgentRegistry(sensenova_claw_home=tmp_path / "agents")
    registry.register(AgentConfig.create(id="default", name="Default"))
    registry.register(AgentConfig.create(id="helper", name="Helper"))
    runtime = AgentRuntime(
        bus_router=bus_router,
        repo=repo,
        context_builder=ContextBuilder(),
        tool_registry=ToolRegistry(),
        state_store=SessionStateStore(),
        agent_registry=registry,
    )
    coordinator = AgentMessageCoordinator(bus=bus, repo=repo, agent_runtime=runtime)
    await bus_router.start()
    await runtime.start()
    await coordinator.start()
    return bus, bus_router, registry, runtime, coordinator


class TestSendMessageTool:
    async def test_send_message_blocked_when_delegation_disabled(self, test_repo, tmp_path):
        bus, bus_router, registry, runtime, coordinator = await _build_runtime(test_repo, tmp_path)
        registry.register(AgentConfig.create(id="default", name="Default", can_send_message_to=None))
        await test_repo.create_session("parent", meta={"agent_id": "default"})

        tool = SendMessageTool(
            agent_registry=registry,
            bus=bus,
            repo=test_repo,
            coordinator=coordinator,
            timeout=5,
        )
        result = await tool.execute(
            target_agent="helper",
            message="请处理",
            _session_id="parent",
            _turn_id="turn_parent",
            _tool_call_id="tool_1",
        )

        assert result == "发送失败：当前 Agent 未被授权向任何 Agent 发送消息。"

        await coordinator.stop()
        await runtime.stop()
        await bus_router.stop()

    async def test_sync_send_message_success(self, test_repo, tmp_path):
        bus, bus_router, registry, runtime, coordinator = await _build_runtime(test_repo, tmp_path)
        await test_repo.create_session("parent", meta={"agent_id": "default"})

        seen_child_session_id: dict[str, str] = {}

        async def fake_child_agent():
            async for event in bus.subscribe():
                if event.type == USER_INPUT and event.session_id.startswith("agent2agent_"):
                    seen_child_session_id["value"] = event.session_id
                    await asyncio.sleep(0.05)
                    await bus.publish(
                        EventEnvelope(
                            type=AGENT_STEP_COMPLETED,
                            session_id=event.session_id,
                            source="test",
                            payload={"result": {"content": "done"}},
                        )
                    )
                    return

        fake_task = asyncio.create_task(fake_child_agent())
        await asyncio.sleep(0)

        tool = SendMessageTool(
            agent_registry=registry,
            bus=bus,
            repo=test_repo,
            coordinator=coordinator,
            timeout=5,
        )
        result = await tool.execute(
            target_agent="helper",
            message="请处理",
            _session_id="parent",
            _turn_id="turn_parent",
            _tool_call_id="tool_1",
        )

        assert "done" in result
        assert "session_id=" in result
        child_session_id = seen_child_session_id["value"]
        record = await test_repo.get_message_record_by_child_session(child_session_id)
        assert record is not None
        assert record.status == "completed"
        assert record.result == "done"

        fake_task.cancel()
        await coordinator.stop()
        await runtime.stop()
        await bus_router.stop()

    async def test_async_send_message_publishes_completion_event(self, test_repo, tmp_path):
        bus, bus_router, registry, runtime, coordinator = await _build_runtime(test_repo, tmp_path)
        await test_repo.create_session("parent", meta={"agent_id": "default"})

        completed_event: dict[str, EventEnvelope] = {}
        done = asyncio.Event()

        async def collector():
            async for event in bus.subscribe():
                if event.type == AGENT_MESSAGE_COMPLETED and event.session_id == "parent":
                    completed_event["value"] = event
                    done.set()
                    return

        async def fake_child_agent():
            async for event in bus.subscribe():
                if event.type == USER_INPUT and event.session_id.startswith("agent2agent_"):
                    await asyncio.sleep(0.05)
                    await bus.publish(
                        EventEnvelope(
                            type=AGENT_STEP_COMPLETED,
                            session_id=event.session_id,
                            source="test",
                            payload={"result": {"content": "async done"}},
                        )
                    )
                    return

        collector_task = asyncio.create_task(collector())
        fake_task = asyncio.create_task(fake_child_agent())
        await asyncio.sleep(0)

        tool = SendMessageTool(
            agent_registry=registry,
            bus=bus,
            repo=test_repo,
            coordinator=coordinator,
            timeout=5,
        )
        result = await tool.execute(
            target_agent="helper",
            message="异步处理",
            mode="async",
            _session_id="parent",
            _turn_id="turn_parent",
            _tool_call_id="tool_1",
        )

        assert "结果会自动回传" in result
        await asyncio.wait_for(done.wait(), timeout=5)
        assert completed_event["value"].payload["result"] == "async done"

        collector_task.cancel()
        fake_task.cancel()
        await coordinator.stop()
        await runtime.stop()
        await bus_router.stop()

    async def test_sync_send_message_waits_for_ask_user_answer(self, test_repo, tmp_path):
        bus, bus_router, registry, runtime, coordinator = await _build_runtime(test_repo, tmp_path)
        await test_repo.create_session("parent", meta={"agent_id": "default"})

        child_session: dict[str, str] = {}
        asked = asyncio.Event()
        answered = asyncio.Event()
        question_id = "q_child_confirm"

        async def fake_child_agent():
            async for event in bus.subscribe():
                if event.type == USER_INPUT and event.session_id.startswith("agent2agent_"):
                    child_session["value"] = event.session_id
                    await bus.publish(
                        EventEnvelope(
                            type=USER_QUESTION_ASKED,
                            session_id=event.session_id,
                            source="test",
                            payload={
                                "question_id": question_id,
                                "question": "请确认环境",
                                "options": ["dev", "prod"],
                                "multi_select": False,
                                "timeout": 300,
                            },
                        )
                    )
                    asked.set()
                    continue

                if (
                    event.type == USER_QUESTION_ANSWERED
                    and child_session.get("value")
                    and event.session_id == child_session["value"]
                    and event.payload.get("question_id") == question_id
                ):
                    answered.set()
                    answer = str(event.payload.get("answer", ""))
                    await bus.publish(
                        EventEnvelope(
                            type=AGENT_STEP_COMPLETED,
                            session_id=event.session_id,
                            source="test",
                            payload={"result": {"content": f"已收到回答: {answer}"}},
                        )
                    )
                    return

        fake_task = asyncio.create_task(fake_child_agent())
        await asyncio.sleep(0)

        tool = SendMessageTool(
            agent_registry=registry,
            bus=bus,
            repo=test_repo,
            coordinator=coordinator,
            timeout=5,
        )
        run_task = asyncio.create_task(
            tool.execute(
                target_agent="helper",
                message="请先提问再处理",
                _session_id="parent",
                _turn_id="turn_parent",
                _tool_call_id="tool_ask_user",
            )
        )

        await asyncio.wait_for(asked.wait(), timeout=5)
        await bus.publish(
            EventEnvelope(
                type=USER_QUESTION_ANSWERED,
                session_id=child_session["value"],
                source="test",
                payload={
                    "question_id": question_id,
                    "answer": "prod",
                    "cancelled": False,
                },
            )
        )

        result = await asyncio.wait_for(run_task, timeout=5)
        assert answered.is_set() is True
        assert "已收到回答: prod" in result

        record = await test_repo.get_message_record_by_child_session(child_session["value"])
        assert record is not None
        assert record.status == "completed"

        fake_task.cancel()
        await coordinator.stop()
        await runtime.stop()
        await bus_router.stop()

    async def test_depth_limit(self, test_repo, tmp_path):
        bus, bus_router, registry, runtime, coordinator = await _build_runtime(test_repo, tmp_path)
        registry.register(AgentConfig.create(id="orchestrator", name="Orchestrator", max_send_depth=1))
        await test_repo.create_session(
            "deep_parent",
            meta={"agent_id": "orchestrator", "send_depth": 1},
        )

        tool = SendMessageTool(
            agent_registry=registry,
            bus=bus,
            repo=test_repo,
            coordinator=coordinator,
            timeout=5,
        )
        result = await tool.execute(
            target_agent="helper",
            message="继续嵌套",
            _session_id="deep_parent",
            _turn_id="turn_parent",
            _tool_call_id="tool_1",
        )

        assert "最大消息传递深度" in result

        await coordinator.stop()
        await runtime.stop()
        await bus_router.stop()

    async def test_retry_on_child_failure_then_success(self, test_repo, tmp_path):
        bus, bus_router, registry, runtime, coordinator = await _build_runtime(test_repo, tmp_path)
        await test_repo.create_session("parent", meta={"agent_id": "default"})

        child_session_id: dict[str, str] = {}
        attempt_counter = 0

        async def fake_child_agent():
            nonlocal attempt_counter
            async for event in bus.subscribe():
                if event.type != USER_INPUT or not event.session_id.startswith("agent2agent_"):
                    continue
                child_session_id["value"] = event.session_id
                attempt_counter += 1
                if attempt_counter == 1:
                    await bus.publish(
                        EventEnvelope(
                            type=ERROR_RAISED,
                            session_id=event.session_id,
                            turn_id=event.turn_id,
                            source="test",
                            payload={"error_type": "RuntimeError", "error_message": "first boom"},
                        )
                    )
                    continue
                await bus.publish(
                    EventEnvelope(
                        type=AGENT_STEP_COMPLETED,
                        session_id=event.session_id,
                        turn_id=event.turn_id,
                        source="test",
                        payload={"result": {"content": "retry done"}},
                    )
                )
                return

        fake_task = asyncio.create_task(fake_child_agent())
        await asyncio.sleep(0)

        tool = SendMessageTool(
            agent_registry=registry,
            bus=bus,
            repo=test_repo,
            coordinator=coordinator,
            timeout=5,
            default_max_retries=0,
        )
        result = await tool.execute(
            target_agent="helper",
            message="重试一下",
            max_retries=1,
            timeout_seconds=2,
            _session_id="parent",
            _turn_id="turn_parent",
            _tool_call_id="tool_retry",
        )

        assert "retry done" in result
        assert attempt_counter == 2
        record = await test_repo.get_message_record_by_child_session(child_session_id["value"])
        assert record is not None
        assert record.status == "completed"
        assert record.attempt_count == 2

        fake_task.cancel()
        await coordinator.stop()
        await runtime.stop()
        await bus_router.stop()

    async def test_sync_timeout_cancels_child_session(self, test_repo, tmp_path):
        bus, bus_router, registry, runtime, coordinator = await _build_runtime(test_repo, tmp_path)
        await test_repo.create_session("parent", meta={"agent_id": "default"})

        seen_child_session: dict[str, str] = {}
        seen_cancel = asyncio.Event()

        async def collector():
            async for event in bus.subscribe():
                if event.type == USER_INPUT and event.session_id.startswith("agent2agent_"):
                    seen_child_session["value"] = event.session_id
                if (
                    event.type == USER_TURN_CANCEL_REQUESTED
                    and seen_child_session.get("value")
                    and event.session_id == seen_child_session["value"]
                ):
                    seen_cancel.set()
                    return

        collector_task = asyncio.create_task(collector())
        await asyncio.sleep(0)

        tool = SendMessageTool(
            agent_registry=registry,
            bus=bus,
            repo=test_repo,
            coordinator=coordinator,
            timeout=5,
            default_max_retries=0,
        )
        result = await tool.execute(
            target_agent="helper",
            message="会超时",
            timeout_seconds=0.05,
            _session_id="parent",
            _turn_id="turn_parent",
            _tool_call_id="tool_timeout",
        )

        assert "处理超时" in result
        await asyncio.wait_for(seen_cancel.wait(), timeout=5)
        record = await test_repo.get_message_record_by_child_session(seen_child_session["value"])
        assert record is not None
        assert record.status == "timed_out"

        collector_task.cancel()
        await coordinator.stop()
        await runtime.stop()
        await bus_router.stop()

    async def test_self_delegation_allowed(self, test_repo, tmp_path):
        """agent 向自己发送消息（自我委派）应被允许"""
        bus, bus_router, registry, runtime, coordinator = await _build_runtime(test_repo, tmp_path)
        registry.register(AgentConfig.create(id="searcher", name="Searcher", max_send_depth=2))
        await test_repo.create_session(
            "parent",
            meta={"agent_id": "searcher", "send_depth": 0, "send_chain": ["searcher"]},
        )

        seen_child = asyncio.Event()

        async def fake_child():
            async for event in bus.subscribe():
                if event.type == USER_INPUT and event.session_id.startswith("agent2agent_"):
                    seen_child.set()
                    await bus.publish(
                        EventEnvelope(
                            type=AGENT_STEP_COMPLETED,
                            session_id=event.session_id,
                            source="test",
                            payload={"result": {"content": "self-delegated result"}},
                        )
                    )
                    return

        fake_task = asyncio.create_task(fake_child())
        await asyncio.sleep(0)

        tool = SendMessageTool(
            agent_registry=registry,
            bus=bus,
            repo=test_repo,
            coordinator=coordinator,
            timeout=5,
        )
        result = await tool.execute(
            target_agent="searcher",
            message="子任务",
            _session_id="parent",
            _turn_id="turn_1",
            _tool_call_id="tc_1",
        )

        assert "self-delegated result" in result
        assert seen_child.is_set()

        fake_task.cancel()
        await coordinator.stop()
        await runtime.stop()
        await bus_router.stop()

    async def test_real_cycle_still_blocked(self, test_repo, tmp_path):
        """真正的循环（A→B→A）仍应被拦截"""
        bus, bus_router, registry, runtime, coordinator = await _build_runtime(test_repo, tmp_path)
        registry.register(AgentConfig.create(id="agent_a", name="A", max_send_depth=3))
        registry.register(AgentConfig.create(id="agent_b", name="B", max_send_depth=3))
        await test_repo.create_session(
            "b_session",
            meta={"agent_id": "agent_b", "send_depth": 1, "send_chain": ["agent_a", "agent_b"]},
        )

        tool = SendMessageTool(
            agent_registry=registry,
            bus=bus,
            repo=test_repo,
            coordinator=coordinator,
            timeout=5,
        )
        result = await tool.execute(
            target_agent="agent_a",
            message="回环",
            _session_id="b_session",
            _turn_id="turn_b",
            _tool_call_id="tc_b",
        )

        assert "循环链路" in result

        await coordinator.stop()
        await runtime.stop()
        await bus_router.stop()

    async def test_parallel_self_delegation(self, test_repo, tmp_path):
        """多目标并行自我委派应全部成功"""
        bus, bus_router, registry, runtime, coordinator = await _build_runtime(test_repo, tmp_path)
        registry.register(AgentConfig.create(id="searcher", name="Searcher", max_send_depth=2))
        await test_repo.create_session(
            "parent",
            meta={"agent_id": "searcher", "send_depth": 0, "send_chain": ["searcher"]},
        )

        child_count = 0

        async def fake_children():
            nonlocal child_count
            async for event in bus.subscribe():
                if event.type == USER_INPUT and event.session_id.startswith("agent2agent_"):
                    child_count += 1
                    await bus.publish(
                        EventEnvelope(
                            type=AGENT_STEP_COMPLETED,
                            session_id=event.session_id,
                            source="test",
                            payload={"result": {"content": f"result-{child_count}"}},
                        )
                    )
                    if child_count >= 3:
                        return

        fake_task = asyncio.create_task(fake_children())
        await asyncio.sleep(0)

        tool = SendMessageTool(
            agent_registry=registry,
            bus=bus,
            repo=test_repo,
            coordinator=coordinator,
            timeout=5,
        )
        result = await tool.execute(
            targets=[
                {"target_agent": "searcher", "message": "[子任务模式] 任务1"},
                {"target_agent": "searcher", "message": "[子任务模式] 任务2"},
                {"target_agent": "searcher", "message": "[子任务模式] 任务3"},
            ],
            mode="sync",
            timeout_seconds=5,
            _session_id="parent",
            _turn_id="turn_1",
            _tool_call_id="tc_1",
        )

        assert isinstance(result, list)
        assert len(result) == 3
        assert all(r["status"] == "completed" for r in result)

        fake_task.cancel()
        await coordinator.stop()
        await runtime.stop()
        await bus_router.stop()
