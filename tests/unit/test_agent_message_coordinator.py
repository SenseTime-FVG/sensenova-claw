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

    async def test_no_heartbeat_triggers_timeout(self, test_repo):
        """子 Agent 无活动超过 timeout 应触发超时"""
        bus = PublicEventBus()
        runtime = _FakeAgentRuntime()
        coordinator = AgentMessageCoordinator(
            bus=bus, repo=test_repo, agent_runtime=runtime,
        )
        await coordinator.start()
        await asyncio.sleep(0)  # let event loop subscribe
        waiter = coordinator.register_sync_waiter("record_no_hb")

        await bus.publish(EventEnvelope(
            type=AGENT_MESSAGE_REQUESTED,
            session_id="parent",
            trace_id="record_no_hb",
            payload={
                "record_id": "record_no_hb",
                "target_id": "helper",
                "message": "无心跳任务",
                "mode": "sync",
                "depth": 1,
                "send_chain": ["default"],
                "parent_session_id": "parent",
                "timeout_seconds": 0.3,
                "max_retries": 0,
            },
        ))
        # No heartbeats sent, wait for timeout
        payload = await asyncio.wait_for(waiter, timeout=5)
        assert payload["status"] == "timed_out"

        record = await test_repo.get_message_record("record_no_hb")
        assert record is not None
        assert record.status == "timed_out"
        await coordinator.stop()

    async def test_heartbeat_cleanup_on_completion(self, test_repo):
        """任务完成后 _last_heartbeat 应被清理"""
        bus = PublicEventBus()
        runtime = _FakeAgentRuntime()
        coordinator = AgentMessageCoordinator(
            bus=bus, repo=test_repo, agent_runtime=runtime,
        )
        await coordinator.start()
        await asyncio.sleep(0)  # let event loop subscribe

        await bus.publish(EventEnvelope(
            type=AGENT_MESSAGE_REQUESTED,
            session_id="parent",
            trace_id="record_cleanup",
            payload={
                "record_id": "record_cleanup",
                "target_id": "helper",
                "message": "清理测试",
                "mode": "async",
                "depth": 1,
                "send_chain": ["default"],
                "parent_session_id": "parent",
                "timeout_seconds": 30,
                "max_retries": 0,
            },
        ))
        await asyncio.sleep(0.1)
        assert "record_cleanup" in coordinator._last_heartbeat

        record = await test_repo.get_message_record("record_cleanup")
        await bus.publish(EventEnvelope(
            type=AGENT_STEP_COMPLETED,
            session_id=record.child_session_id,
            turn_id=record.active_turn_id,
            payload={"result": {"content": "done"}},
        ))
        await asyncio.sleep(0.1)
        assert "record_cleanup" not in coordinator._last_heartbeat
        await coordinator.stop()

    async def test_heartbeat_isolation_between_records(self, test_repo):
        """两个并行 delegation，一个有心跳一个没有，验证互不影响"""
        bus = PublicEventBus()
        runtime = _FakeAgentRuntime()
        coordinator = AgentMessageCoordinator(
            bus=bus, repo=test_repo, agent_runtime=runtime,
        )
        await coordinator.start()
        await asyncio.sleep(0)  # let event loop subscribe
        waiter_a = coordinator.register_sync_waiter("record_a")

        # Create record_a (short timeout, no heartbeat → should timeout)
        await bus.publish(EventEnvelope(
            type=AGENT_MESSAGE_REQUESTED,
            session_id="parent",
            trace_id="record_a",
            payload={
                "record_id": "record_a",
                "target_id": "helper",
                "message": "任务A",
                "mode": "sync",
                "depth": 1,
                "send_chain": ["default"],
                "parent_session_id": "parent",
                "timeout_seconds": 0.3,
                "max_retries": 0,
            },
        ))
        await asyncio.sleep(0.05)

        # Create record_b (longer timeout, with heartbeat → should NOT timeout)
        await bus.publish(EventEnvelope(
            type=AGENT_MESSAGE_REQUESTED,
            session_id="parent2",
            trace_id="record_b",
            payload={
                "record_id": "record_b",
                "target_id": "helper",
                "message": "任务B",
                "mode": "async",
                "depth": 1,
                "send_chain": ["default"],
                "parent_session_id": "parent2",
                "timeout_seconds": 2.0,
                "max_retries": 0,
            },
        ))
        await asyncio.sleep(0.05)

        record_b = await test_repo.get_message_record("record_b")
        child_b = record_b.child_session_id

        # Only send heartbeats to record_b
        for _ in range(3):
            await asyncio.sleep(0.15)
            await bus.publish(EventEnvelope(
                type=TOOL_CALL_COMPLETED,
                session_id=child_b,
                payload={},
            ))

        # record_a should have timed out
        payload_a = await asyncio.wait_for(waiter_a, timeout=5)
        assert payload_a["status"] == "timed_out"

        # record_b should still be running
        record_b = await test_repo.get_message_record("record_b")
        assert record_b.status == "running"
        await coordinator.stop()

    async def test_unrelated_session_heartbeat_ignored(self, test_repo):
        """非子 session 的心跳事件不应影响任何 record 的计时器"""
        bus = PublicEventBus()
        runtime = _FakeAgentRuntime()
        coordinator = AgentMessageCoordinator(
            bus=bus, repo=test_repo, agent_runtime=runtime,
        )
        await coordinator.start()
        await asyncio.sleep(0)  # let event loop subscribe
        waiter = coordinator.register_sync_waiter("record_unrelated")

        await bus.publish(EventEnvelope(
            type=AGENT_MESSAGE_REQUESTED,
            session_id="parent",
            trace_id="record_unrelated",
            payload={
                "record_id": "record_unrelated",
                "target_id": "helper",
                "message": "无关测试",
                "mode": "sync",
                "depth": 1,
                "send_chain": ["default"],
                "parent_session_id": "parent",
                "timeout_seconds": 0.3,
                "max_retries": 0,
            },
        ))
        await asyncio.sleep(0.05)

        # Send heartbeats from unrelated session
        for _ in range(3):
            await asyncio.sleep(0.15)
            await bus.publish(EventEnvelope(
                type=LLM_CALL_REQUESTED,
                session_id="totally_unrelated_session",
                payload={},
            ))

        # Should still timeout (unrelated heartbeats don't renew)
        payload = await asyncio.wait_for(waiter, timeout=5)
        assert payload["status"] == "timed_out"
        await coordinator.stop()

    async def test_heartbeat_bubbles_up_to_ancestor(self, test_repo):
        """多层委托 A→B→C 时，C 的心跳应续期 B→C 和 A→B 两条 record"""
        bus = PublicEventBus()
        runtime = _FakeAgentRuntime()
        coordinator = AgentMessageCoordinator(
            bus=bus, repo=test_repo, agent_runtime=runtime,
        )

        # 第一层：A→B（record_ab, parent=session_A, child=session_B）
        await coordinator._handle_message_requested(EventEnvelope(
            type=AGENT_MESSAGE_REQUESTED,
            session_id="session_A",
            trace_id="record_ab",
            payload={
                "record_id": "record_ab",
                "target_id": "agent_B",
                "message": "A→B",
                "mode": "sync",
                "depth": 1,
                "send_chain": ["A"],
                "parent_session_id": "session_A",
                "timeout_seconds": 0.5,
                "max_retries": 0,
            },
        ))
        record_ab = await test_repo.get_message_record("record_ab")
        child_b_sid = record_ab.child_session_id

        # 第二层：B→C（record_bc, parent=session_B(=child_b_sid), child=session_C）
        await coordinator._handle_message_requested(EventEnvelope(
            type=AGENT_MESSAGE_REQUESTED,
            session_id=child_b_sid,
            trace_id="record_bc",
            payload={
                "record_id": "record_bc",
                "target_id": "agent_C",
                "message": "B→C",
                "mode": "sync",
                "depth": 2,
                "send_chain": ["A", "B"],
                "parent_session_id": child_b_sid,
                "timeout_seconds": 0.5,
                "max_retries": 0,
            },
        ))
        record_bc = await test_repo.get_message_record("record_bc")
        child_c_sid = record_bc.child_session_id

        # 验证索引已建立
        assert coordinator._record_parent_session["record_ab"] == "session_A"
        assert coordinator._record_parent_session["record_bc"] == child_b_sid
        assert coordinator._child_session_index[child_b_sid] == "record_ab"
        assert coordinator._child_session_index[child_c_sid] == "record_bc"

        import time
        # 记录初始心跳时间
        initial_ab = coordinator._last_heartbeat["record_ab"]
        initial_bc = coordinator._last_heartbeat["record_bc"]

        await asyncio.sleep(0.05)

        # C 发出心跳 → 应同时续期 record_bc 和 record_ab
        coordinator._renew_heartbeat_chain(child_c_sid)

        assert coordinator._last_heartbeat["record_bc"] > initial_bc
        assert coordinator._last_heartbeat["record_ab"] > initial_ab
        # 两者应该被设为相同的 now
        assert coordinator._last_heartbeat["record_ab"] == coordinator._last_heartbeat["record_bc"]

        await coordinator.stop()

    async def test_heartbeat_bubble_prevents_ancestor_timeout(self, test_repo):
        """多层委托中，子 agent 活动应阻止祖父级超时"""
        bus = PublicEventBus()
        runtime = _FakeAgentRuntime()
        coordinator = AgentMessageCoordinator(
            bus=bus, repo=test_repo, agent_runtime=runtime,
        )
        await coordinator.start()
        await asyncio.sleep(0)

        waiter_ab = coordinator.register_sync_waiter("record_ab2")

        # A→B（timeout=1s，给心跳冒泡留充足余量）
        await bus.publish(EventEnvelope(
            type=AGENT_MESSAGE_REQUESTED,
            session_id="session_A2",
            trace_id="record_ab2",
            payload={
                "record_id": "record_ab2",
                "target_id": "agent_B",
                "message": "A→B",
                "mode": "sync",
                "depth": 1,
                "send_chain": ["A"],
                "parent_session_id": "session_A2",
                "timeout_seconds": 1.0,
                "max_retries": 0,
            },
        ))
        await asyncio.sleep(0.1)
        record_ab = await test_repo.get_message_record("record_ab2")
        child_b_sid = record_ab.child_session_id

        # B→C
        await bus.publish(EventEnvelope(
            type=AGENT_MESSAGE_REQUESTED,
            session_id=child_b_sid,
            trace_id="record_bc2",
            payload={
                "record_id": "record_bc2",
                "target_id": "agent_C",
                "message": "B→C",
                "mode": "sync",
                "depth": 2,
                "send_chain": ["A", "B"],
                "parent_session_id": child_b_sid,
                "timeout_seconds": 1.0,
                "max_retries": 0,
            },
        ))
        await asyncio.sleep(0.1)
        record_bc = await test_repo.get_message_record("record_bc2")
        child_c_sid = record_bc.child_session_id

        # C 持续发心跳，总时长 > timeout（1s），每次间隔 < timeout/3
        for _ in range(6):
            await asyncio.sleep(0.2)
            await bus.publish(EventEnvelope(
                type=TOOL_CALL_COMPLETED,
                session_id=child_c_sid,
                payload={},
            ))
            await asyncio.sleep(0.02)  # 让 coordinator 处理事件

        # A→B 不应超时（因为 C 的心跳冒泡续期了 record_ab2）
        record_ab = await test_repo.get_message_record("record_ab2")
        assert record_ab.status == "running", f"Expected running but got {record_ab.status}"

        # 手动完成 B→C 和 A→B
        await bus.publish(EventEnvelope(
            type=AGENT_STEP_COMPLETED,
            session_id=child_c_sid,
            turn_id=record_bc.active_turn_id,
            payload={"result": {"content": "C done"}},
        ))
        await asyncio.sleep(0.1)
        await bus.publish(EventEnvelope(
            type=AGENT_STEP_COMPLETED,
            session_id=child_b_sid,
            turn_id=record_ab.active_turn_id,
            payload={"result": {"content": "B done"}},
        ))
        payload = await asyncio.wait_for(waiter_ab, timeout=5)
        assert payload["status"] == "completed"
        await coordinator.stop()
