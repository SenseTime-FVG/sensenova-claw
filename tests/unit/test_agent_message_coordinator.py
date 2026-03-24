"""AgentMessageCoordinator 单元测试。"""
from __future__ import annotations

import asyncio

import pytest

from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import (
    AGENT_MESSAGE_REQUESTED,
    AGENT_STEP_COMPLETED,
    ERROR_RAISED,
    LLM_CALL_REQUESTED,
    TOOL_CALL_COMPLETED,
    USER_TURN_CANCEL_REQUESTED,
)
from sensenova_claw.kernel.runtime.agent_message_coordinator import AgentMessageCoordinator

pytestmark = pytest.mark.asyncio


class _FakeBusRouter:
    def __init__(self):
        self._destroy_callbacks = []
        self.touched: list[str] = []

    def on_destroy(self, callback):
        self._destroy_callbacks.append(callback)

    def touch(self, session_id: str) -> None:
        self.touched.append(session_id)


class _FakeAgentRuntime:
    def __init__(self):
        self.bus_router = _FakeBusRouter()
        self.spawn_calls: list[dict] = []
        self.send_calls: list[dict] = []

    async def spawn_agent_session(self, **kwargs):
        self.spawn_calls.append(kwargs)
        return "turn_spawn_1"

    async def send_user_input(self, **kwargs):
        self.send_calls.append(kwargs)
        return f"turn_retry_{len(self.send_calls)}"


async def _collect_event(bus: PublicEventBus, event_type: str, session_id: str | None = None):
    done = asyncio.Event()
    seen: dict[str, EventEnvelope] = {}

    async def _collector():
        async for event in bus.subscribe():
            if event.type != event_type:
                continue
            if session_id and event.session_id != session_id:
                continue
            seen["value"] = event
            done.set()
            return

    task = asyncio.create_task(_collector())
    await asyncio.sleep(0)
    return seen, done, task


class TestAgentMessageCoordinator:
    async def test_requested_creates_record_and_spawns_child(self, test_repo):
        bus = PublicEventBus()
        runtime = _FakeAgentRuntime()
        coordinator = AgentMessageCoordinator(
            bus=bus,
            repo=test_repo,
            agent_runtime=runtime,
            retry_backoff_seconds=[0],
        )

        event = EventEnvelope(
            type=AGENT_MESSAGE_REQUESTED,
            session_id="parent",
            trace_id="record_1",
            payload={
                "record_id": "record_1",
                "target_id": "helper",
                "message": "请处理",
                "mode": "sync",
                "depth": 1,
                "send_chain": ["default"],
                "parent_session_id": "parent",
                "parent_turn_id": "turn_parent",
                "parent_tool_call_id": "tool_1",
                "timeout_seconds": 30,
                "max_retries": 2,
            },
        )

        await coordinator._handle_message_requested(event)

        record = await test_repo.get_message_record("record_1")
        assert record is not None
        assert record.status == "running"
        assert record.child_session_id.startswith("agent2agent_")
        assert record.active_turn_id == "turn_spawn_1"
        assert record.attempt_count == 1
        assert record.max_attempts == 3
        assert record.timeout_seconds == 30
        assert runtime.spawn_calls[0]["trace_id"] == "record_1"
        await coordinator.stop()

    async def test_retry_ignores_stale_completion_and_succeeds(self, test_repo):
        bus = PublicEventBus()
        runtime = _FakeAgentRuntime()
        coordinator = AgentMessageCoordinator(
            bus=bus,
            repo=test_repo,
            agent_runtime=runtime,
            retry_backoff_seconds=[0],
        )

        await coordinator._handle_message_requested(
            EventEnvelope(
                type=AGENT_MESSAGE_REQUESTED,
                session_id="parent",
                trace_id="record_retry",
                payload={
                    "record_id": "record_retry",
                    "target_id": "helper",
                    "message": "重试任务",
                    "mode": "sync",
                    "depth": 1,
                    "send_chain": ["default"],
                    "parent_session_id": "parent",
                    "timeout_seconds": 30,
                    "max_retries": 1,
                },
            )
        )
        record = await test_repo.get_message_record("record_retry")
        assert record is not None
        first_turn_id = record.active_turn_id

        await coordinator._handle_child_failed(
            EventEnvelope(
                type=ERROR_RAISED,
                session_id=record.child_session_id,
                turn_id=first_turn_id,
                payload={"error_type": "RuntimeError", "error_message": "boom"},
            )
        )
        await asyncio.sleep(0.05)

        record = await test_repo.get_message_record("record_retry")
        assert record is not None
        assert record.status == "running"
        assert record.attempt_count == 2
        assert record.active_turn_id == "turn_retry_1"
        assert len(runtime.send_calls) == 1

        await coordinator._handle_child_completed(
            EventEnvelope(
                type=AGENT_STEP_COMPLETED,
                session_id=record.child_session_id,
                turn_id=first_turn_id,
                payload={"result": {"content": "stale"}},
            )
        )
        record = await test_repo.get_message_record("record_retry")
        assert record is not None
        assert record.status == "running"

        await coordinator._handle_child_completed(
            EventEnvelope(
                type=AGENT_STEP_COMPLETED,
                session_id=record.child_session_id,
                turn_id=record.active_turn_id,
                payload={"result": {"content": "done"}},
            )
        )
        record = await test_repo.get_message_record("record_retry")
        assert record is not None
        assert record.status == "completed"
        assert record.result == "done"
        await coordinator.stop()

    async def test_cancel_requested_propagates_to_child(self, test_repo):
        bus = PublicEventBus()
        runtime = _FakeAgentRuntime()
        coordinator = AgentMessageCoordinator(
            bus=bus,
            repo=test_repo,
            agent_runtime=runtime,
            retry_backoff_seconds=[0],
        )

        await coordinator._handle_message_requested(
            EventEnvelope(
                type=AGENT_MESSAGE_REQUESTED,
                session_id="parent",
                trace_id="record_cancel",
                payload={
                    "record_id": "record_cancel",
                    "target_id": "helper",
                    "message": "取消任务",
                    "mode": "async",
                    "depth": 1,
                    "send_chain": ["default"],
                    "parent_session_id": "parent",
                    "timeout_seconds": 30,
                    "max_retries": 0,
                },
            )
        )
        record = await test_repo.get_message_record("record_cancel")
        assert record is not None

        seen, done, task = await _collect_event(
            bus,
            event_type=USER_TURN_CANCEL_REQUESTED,
            session_id=record.child_session_id,
        )
        await coordinator._handle_cancel_requested(
            EventEnvelope(
                type=USER_TURN_CANCEL_REQUESTED,
                session_id="parent",
                payload={"reason": "user_stop"},
            )
        )
        await asyncio.wait_for(done.wait(), timeout=5)
        task.cancel()

        record = await test_repo.get_message_record("record_cancel")
        assert record is not None
        assert record.status == "cancelled"
        assert seen["value"].payload["reason"] == "父会话取消：user_stop"
        await coordinator.stop()

    async def test_timeout_watch_marks_record_timed_out(self, test_repo):
        bus = PublicEventBus()
        runtime = _FakeAgentRuntime()
        coordinator = AgentMessageCoordinator(
            bus=bus,
            repo=test_repo,
            agent_runtime=runtime,
            retry_backoff_seconds=[0],
        )
        waiter = coordinator.register_sync_waiter("record_timeout")

        await coordinator._handle_message_requested(
            EventEnvelope(
                type=AGENT_MESSAGE_REQUESTED,
                session_id="parent",
                trace_id="record_timeout",
                payload={
                    "record_id": "record_timeout",
                    "target_id": "helper",
                    "message": "超时任务",
                    "mode": "sync",
                    "depth": 1,
                    "send_chain": ["default"],
                    "parent_session_id": "parent",
                    "timeout_seconds": 0.05,
                    "max_retries": 0,
                },
            )
        )
        payload = await asyncio.wait_for(waiter, timeout=5)

        record = await test_repo.get_message_record("record_timeout")
        assert record is not None
        assert record.status == "timed_out"
        assert payload["status"] == "timed_out"
        await coordinator.stop()

    async def test_heartbeat_resets_timeout(self, test_repo):
        """子 Agent 有心跳时不应超时"""
        bus = PublicEventBus()
        runtime = _FakeAgentRuntime()
        coordinator = AgentMessageCoordinator(
            bus=bus, repo=test_repo, agent_runtime=runtime,
        )
        await coordinator.start()
        await asyncio.sleep(0)  # let event loop subscribe
        waiter = coordinator.register_sync_waiter("record_hb")

        await bus.publish(EventEnvelope(
            type=AGENT_MESSAGE_REQUESTED,
            session_id="parent",
            trace_id="record_hb",
            payload={
                "record_id": "record_hb",
                "target_id": "helper",
                "message": "心跳任务",
                "mode": "sync",
                "depth": 1,
                "send_chain": ["default"],
                "parent_session_id": "parent",
                "timeout_seconds": 0.3,
                "max_retries": 0,
            },
        ))
        await asyncio.sleep(0.1)  # let coordinator process event

        record = await test_repo.get_message_record("record_hb")
        assert record is not None
        child_sid = record.child_session_id

        # Send heartbeats before timeout expires (every 0.15s, 3 times = 0.45s > timeout 0.3s)
        for _ in range(3):
            await asyncio.sleep(0.15)
            await bus.publish(EventEnvelope(
                type=LLM_CALL_REQUESTED,
                session_id=child_sid,
                payload={},
            ))

        # Wait a bit more to confirm no timeout
        await asyncio.sleep(0.1)
        record = await test_repo.get_message_record("record_hb")
        assert record is not None
        assert record.status == "running", f"Expected running but got {record.status}"

        # Manually complete
        await bus.publish(EventEnvelope(
            type=AGENT_STEP_COMPLETED,
            session_id=child_sid,
            turn_id=record.active_turn_id,
            payload={"result": {"content": "done"}},
        ))
        payload = await asyncio.wait_for(waiter, timeout=5)
        assert payload["status"] == "completed"
        await coordinator.stop()
