from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any

from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import (
    AGENT_MESSAGE_COMPLETED,
    AGENT_MESSAGE_FAILED,
    AGENT_MESSAGE_REQUESTED,
    AGENT_STEP_COMPLETED,
    ERROR_RAISED,
    SESSION_CREATED,
    USER_TURN_CANCEL_REQUESTED,
)
from sensenova_claw.kernel.runtime.message_record import MessageRecord

if TYPE_CHECKING:
    from sensenova_claw.adapters.storage.repository import Repository
    from sensenova_claw.kernel.events.bus import PublicEventBus
    from sensenova_claw.kernel.runtime.agent_runtime import AgentRuntime

logger = logging.getLogger(__name__)


class AgentMessageCoordinator:
    """全局轻协调器：负责跨 session 关联、取消传播和重试/超时控制。"""

    FINAL_STATUSES = {"completed", "failed", "cancelled", "timed_out"}

    def __init__(
        self,
        bus: PublicEventBus,
        repo: Repository,
        agent_runtime: AgentRuntime,
        retry_backoff_seconds: list[float] | None = None,
    ):
        self._bus = bus
        self._repo = repo
        self._agent_runtime = agent_runtime
        self._retry_backoff_seconds = retry_backoff_seconds or [0, 1, 3]
        self._task: asyncio.Task | None = None
        self._sync_waiters: dict[str, asyncio.Future] = {}
        self._child_session_index: dict[str, str] = {}
        self._timeout_tasks: dict[str, asyncio.Task] = {}
        self._retry_tasks: dict[str, asyncio.Task] = {}

    async def start(self) -> None:
        self._agent_runtime.bus_router.on_destroy(self._on_session_destroy)
        self._task = asyncio.create_task(self._event_loop())
        logger.info("AgentMessageCoordinator started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        await self._cancel_background_tasks()
        for future in self._sync_waiters.values():
            if not future.done():
                future.cancel()
        self._sync_waiters.clear()
        logger.info("AgentMessageCoordinator stopped")

    def register_sync_waiter(self, record_id: str) -> asyncio.Future:
        future = asyncio.get_running_loop().create_future()
        self._sync_waiters[record_id] = future
        return future

    def cancel_sync_waiter(self, record_id: str) -> None:
        future = self._sync_waiters.pop(record_id, None)
        if future and not future.done():
            future.cancel()

    async def get_record_by_session(self, session_id: str) -> MessageRecord | None:
        record_id = self._child_session_index.get(session_id)
        if record_id:
            record = await self._repo.get_message_record(record_id)
            if record:
                return record
        record = await self._repo.get_message_record_by_child_session(session_id)
        if record:
            self._child_session_index[session_id] = record.id
        return record

    async def get_pingpong_count(self, session_id: str) -> int:
        record = await self.get_record_by_session(session_id)
        if not record:
            return 0
        return record.pingpong_count

    async def cancel_message(
        self,
        record_id: str,
        reason: str,
        status: str = "cancelled",
        propagate_to_child: bool = True,
        source_session_id: str | None = None,
    ) -> bool:
        record = await self._repo.get_message_record(record_id)
        if not record or record.status in self.FINAL_STATUSES:
            return False

        record.status = status
        record.error = reason
        record.completed_at = time.time()
        record.active_turn_id = None
        await self._repo.update_message_record(record)
        self._cancel_record_tasks(record.id)

        payload = self._build_terminal_payload(record)
        await self._resolve_waiter_or_publish(
            record=record,
            payload=payload,
            event_type=AGENT_MESSAGE_FAILED,
        )

        if propagate_to_child:
            await self._publish_child_cancel(
                record=record,
                reason=reason,
                source_session_id=source_session_id,
            )

        logger.info(
            "agent_message cancelled record=%s status=%s child_session=%s source_session=%s reason=%s",
            record.id,
            status,
            record.child_session_id,
            source_session_id,
            reason,
        )
        return True

    async def _event_loop(self) -> None:
        async for event in self._bus.subscribe():
            try:
                if event.type == AGENT_MESSAGE_REQUESTED:
                    await self._handle_message_requested(event)
                elif event.type == AGENT_STEP_COMPLETED:
                    await self._handle_child_completed(event)
                elif event.type == ERROR_RAISED:
                    await self._handle_child_failed(event)
                elif event.type == USER_TURN_CANCEL_REQUESTED:
                    await self._handle_cancel_requested(event)
            except Exception:  # noqa: BLE001
                logger.exception("AgentMessageCoordinator 处理事件失败")

    async def _handle_message_requested(self, event: EventEnvelope) -> None:
        payload = event.payload
        record_id = str(payload["record_id"])
        target_id = str(payload["target_id"])
        message = str(payload["message"])
        mode = str(payload.get("mode", "sync"))
        requested_session_id = payload.get("session_id")
        parent_session_id = str(payload.get("parent_session_id", ""))
        parent_turn_id = payload.get("parent_turn_id")
        parent_tool_call_id = payload.get("parent_tool_call_id")
        depth = int(payload.get("depth", 0))
        timeout_seconds = float(payload.get("timeout_seconds", 300))
        max_attempts = max(int(payload.get("max_retries", 0)) + 1, 1)
        send_chain = list(payload.get("send_chain", []))
        child_session_id = (
            str(requested_session_id)
            if requested_session_id
            else f"agent2agent_{uuid.uuid4().hex[:12]}"
        )

        existing_record = None
        pingpong_count = 0
        if requested_session_id:
            existing_record = await self.get_record_by_session(child_session_id)
            pingpong_count = (existing_record.pingpong_count if existing_record else 0) + 1

        record = MessageRecord(
            id=record_id,
            parent_session_id=parent_session_id,
            parent_turn_id=str(parent_turn_id) if parent_turn_id else None,
            parent_tool_call_id=str(parent_tool_call_id) if parent_tool_call_id else None,
            child_session_id=child_session_id,
            target_id=target_id,
            status="pending",
            mode=mode,
            message=message,
            result=None,
            error=None,
            depth=depth,
            pingpong_count=pingpong_count,
            created_at=time.time(),
            attempt_count=1,
            max_attempts=max_attempts,
            timeout_seconds=timeout_seconds,
        )
        self._child_session_index[child_session_id] = record_id
        await self._repo.save_message_record(record)

        if mode == "async" and parent_session_id:
            self._agent_runtime.bus_router.touch(parent_session_id)

        logger.info(
            "agent_message requested record=%s parent_session=%s child_session=%s target=%s mode=%s timeout=%ss max_attempts=%s",
            record.id,
            record.parent_session_id,
            record.child_session_id,
            record.target_id,
            record.mode,
            timeout_seconds,
            max_attempts,
        )

        try:
            if requested_session_id:
                turn_id = await self._agent_runtime.send_user_input(
                    session_id=child_session_id,
                    user_input=message,
                    trace_id=record.id,
                    extra_payload={
                        "send_depth": depth,
                        "send_chain": send_chain,
                        "record_id": record.id,
                        "attempt_count": record.attempt_count,
                        "max_attempts": record.max_attempts,
                    },
                )
            else:
                meta = {
                    "title": f"[send_message] {message[:30]}",
                    "record_id": record.id,
                    "send_depth": depth,
                    "send_chain": send_chain + [target_id],
                    "parent_turn_id": parent_turn_id,
                    "parent_tool_call_id": parent_tool_call_id,
                    "message_trace_id": record.id,
                }
                turn_id = await self._agent_runtime.spawn_agent_session(
                    agent_id=target_id,
                    session_id=child_session_id,
                    user_input=message,
                    parent_session_id=parent_session_id,
                    trace_id=record.id,
                    meta=meta,
                )
                # 通知前端有新 session 创建
                await self._bus.publish(EventEnvelope(
                    type=SESSION_CREATED,
                    session_id=child_session_id,
                    source="agent_message_coordinator",
                    payload={
                        "session_id": child_session_id,
                        "agent_id": target_id,
                        "meta": meta,
                    },
                ))
        except Exception as exc:  # noqa: BLE001
            logger.exception("agent_message 启动目标会话失败 record=%s", record.id)
            await self.cancel_message(
                record_id=record.id,
                reason=f"启动目标 Agent 失败: {exc}",
                status="failed",
                propagate_to_child=False,
                source_session_id=parent_session_id or None,
            )
            return

        record.status = "running"
        record.active_turn_id = turn_id
        await self._repo.update_message_record(record)
        self._ensure_timeout_watch(record)

    async def _handle_child_completed(self, event: EventEnvelope) -> None:
        record = await self.get_record_by_session(event.session_id)
        if not record or record.status in self.FINAL_STATUSES:
            return
        if record.status == "retrying":
            logger.info(
                "ignore child completion while retrying record=%s session=%s event_turn=%s",
                record.id,
                event.session_id,
                event.turn_id,
            )
            return
        if record.active_turn_id and event.turn_id and event.turn_id != record.active_turn_id:
            logger.info(
                "ignore stale child completion record=%s session=%s event_turn=%s active_turn=%s",
                record.id,
                event.session_id,
                event.turn_id,
                record.active_turn_id,
            )
            return

        result = event.payload.get("result", {})
        content = ""
        if isinstance(result, dict):
            content = str(result.get("content", ""))
        elif result is not None:
            content = str(result)

        record.status = "completed"
        record.result = content
        record.completed_at = time.time()
        await self._repo.update_message_record(record)
        self._cancel_record_tasks(record.id)

        logger.info(
            "agent_message completed record=%s child_session=%s attempts=%s/%s",
            record.id,
            record.child_session_id,
            record.attempt_count,
            record.max_attempts,
        )

        payload = self._build_terminal_payload(record)
        await self._resolve_waiter_or_publish(
            record=record,
            payload=payload,
            event_type=AGENT_MESSAGE_COMPLETED,
        )

    async def _handle_child_failed(self, event: EventEnvelope) -> None:
        record = await self.get_record_by_session(event.session_id)
        if not record or record.status in self.FINAL_STATUSES:
            return
        if record.status == "retrying":
            logger.info(
                "ignore child failure while retrying record=%s session=%s event_turn=%s",
                record.id,
                event.session_id,
                event.turn_id,
            )
            return
        if record.active_turn_id and event.turn_id and event.turn_id != record.active_turn_id:
            logger.info(
                "ignore stale child failure record=%s session=%s event_turn=%s active_turn=%s",
                record.id,
                event.session_id,
                event.turn_id,
                record.active_turn_id,
            )
            return

        error_type = str(event.payload.get("error_type", "UnknownError"))
        error = str(
            event.payload.get("error_message")
            or event.payload.get("error")
            or "未知错误"
        )
        cancelled = bool(event.payload.get("context", {}).get("cancelled"))

        if self._should_retry(record, error_type=error_type, cancelled=cancelled):
            record.status = "retrying"
            record.error = error
            record.active_turn_id = None
            record.attempt_count += 1
            await self._repo.update_message_record(record)
            self._schedule_retry(record)
            logger.warning(
                "agent_message retry scheduled record=%s child_session=%s attempt=%s/%s reason=%s",
                record.id,
                record.child_session_id,
                record.attempt_count,
                record.max_attempts,
                error,
            )
            return

        record.status = "cancelled" if cancelled or error_type == "TurnCancelled" else "failed"
        record.error = error
        record.completed_at = time.time()
        record.active_turn_id = None
        await self._repo.update_message_record(record)
        self._cancel_record_tasks(record.id)

        logger.warning(
            "agent_message failed record=%s child_session=%s attempts=%s/%s error_type=%s error=%s",
            record.id,
            record.child_session_id,
            record.attempt_count,
            record.max_attempts,
            error_type,
            error,
        )

        payload = self._build_terminal_payload(record)
        await self._resolve_waiter_or_publish(
            record=record,
            payload=payload,
            event_type=AGENT_MESSAGE_FAILED,
        )

    async def _handle_cancel_requested(self, event: EventEnvelope) -> None:
        reason = str(event.payload.get("reason", "user_cancel"))
        session_id = event.session_id

        record = await self.get_record_by_session(session_id)
        if record and record.status not in self.FINAL_STATUSES:
            await self.cancel_message(
                record_id=record.id,
                reason=reason,
                status="cancelled",
                propagate_to_child=False,
                source_session_id=session_id,
            )

        active_records = await self._repo.list_active_message_records(parent_session_id=session_id)
        for child_record in active_records:
            await self.cancel_message(
                record_id=child_record.id,
                reason=f"父会话取消：{reason}",
                status="cancelled",
                propagate_to_child=True,
                source_session_id=session_id,
            )

    async def _on_session_destroy(self, session_id: str) -> None:
        record = await self.get_record_by_session(session_id)
        if record and record.status not in self.FINAL_STATUSES:
            await self.cancel_message(
                record_id=record.id,
                reason=f"子会话 {session_id} 已销毁，未完成的 send_message 被终止。",
                status="failed",
                propagate_to_child=False,
                source_session_id=session_id,
            )

        active_records = await self._repo.list_active_message_records(parent_session_id=session_id)
        for child_record in active_records:
            await self.cancel_message(
                record_id=child_record.id,
                reason=f"父会话 {session_id} 已销毁，取消未完成的 send_message。",
                status="cancelled",
                propagate_to_child=True,
                source_session_id=session_id,
            )

        self.cleanup_session(session_id)

    def cleanup_session(self, session_id: str) -> None:
        record_id = self._child_session_index.pop(session_id, None)
        if not record_id:
            return
        self._cancel_record_tasks(record_id)
        future = self._sync_waiters.pop(record_id, None)
        if future and not future.done():
            future.cancel()

    def _ensure_timeout_watch(self, record: MessageRecord) -> None:
        if not record.timeout_seconds or record.timeout_seconds <= 0:
            return
        self._cancel_timeout_task(record.id)
        self._timeout_tasks[record.id] = asyncio.create_task(
            self._timeout_after(record_id=record.id, timeout_seconds=record.timeout_seconds)
        )

    async def _timeout_after(self, record_id: str, timeout_seconds: float) -> None:
        try:
            await asyncio.sleep(timeout_seconds)
            record = await self._repo.get_message_record(record_id)
            if not record or record.status in self.FINAL_STATUSES:
                return
            await self.cancel_message(
                record_id=record_id,
                reason=f"send_message 总超时（{timeout_seconds} 秒）",
                status="timed_out",
                propagate_to_child=True,
                source_session_id=record.parent_session_id or None,
            )
        except asyncio.CancelledError:
            raise
        finally:
            task = self._timeout_tasks.get(record_id)
            if task is asyncio.current_task():
                self._timeout_tasks.pop(record_id, None)

    def _schedule_retry(self, record: MessageRecord) -> None:
        self._cancel_retry_task(record.id)
        retry_index = max(record.attempt_count - 2, 0)
        delay = self._retry_backoff_seconds[min(retry_index, len(self._retry_backoff_seconds) - 1)]
        self._retry_tasks[record.id] = asyncio.create_task(
            self._retry_after_backoff(record_id=record.id, expected_attempt=record.attempt_count, delay=delay)
        )

    async def _retry_after_backoff(
        self,
        record_id: str,
        expected_attempt: int,
        delay: float,
    ) -> None:
        try:
            if delay > 0:
                await asyncio.sleep(delay)
            record = await self._repo.get_message_record(record_id)
            if not record:
                return
            if record.status != "retrying" or record.attempt_count != expected_attempt:
                return
            turn_id = await self._agent_runtime.send_user_input(
                session_id=record.child_session_id,
                user_input=record.message,
                trace_id=record.id,
                extra_payload={
                    "send_depth": record.depth,
                    "record_id": record.id,
                    "attempt_count": record.attempt_count,
                    "max_attempts": record.max_attempts,
                    "retry": True,
                },
            )
            record.status = "running"
            record.active_turn_id = turn_id
            await self._repo.update_message_record(record)
            logger.info(
                "agent_message retry started record=%s child_session=%s turn=%s attempt=%s/%s",
                record.id,
                record.child_session_id,
                turn_id,
                record.attempt_count,
                record.max_attempts,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("agent_message 重试启动失败 record=%s", record_id)
            await self.cancel_message(
                record_id=record_id,
                reason=f"重试启动失败: {exc}",
                status="failed",
                propagate_to_child=False,
            )
        finally:
            task = self._retry_tasks.get(record_id)
            if task is asyncio.current_task():
                self._retry_tasks.pop(record_id, None)

    async def _resolve_waiter_or_publish(
        self,
        record: MessageRecord,
        payload: dict[str, Any],
        event_type: str,
    ) -> None:
        future = self._sync_waiters.pop(record.id, None)
        if future and not future.done():
            future.set_result(payload)
            return

        if not record.parent_session_id:
            return

        self._agent_runtime.bus_router.touch(record.parent_session_id)
        await self._bus.publish(
            EventEnvelope(
                type=event_type,
                session_id=record.parent_session_id,
                trace_id=record.id,
                source="agent_message_coordinator",
                payload=payload,
            )
        )

    async def _publish_child_cancel(
        self,
        record: MessageRecord,
        reason: str,
        source_session_id: str | None,
    ) -> None:
        await self._bus.publish(
            EventEnvelope(
                type=USER_TURN_CANCEL_REQUESTED,
                session_id=record.child_session_id,
                trace_id=record.id,
                source="agent_message_coordinator",
                payload={
                    "reason": reason,
                    "record_id": record.id,
                    "parent_session_id": record.parent_session_id,
                    "parent_tool_call_id": record.parent_tool_call_id,
                    "child_session_id": record.child_session_id,
                    "target_agent": record.target_id,
                    "cancelled_by_session_id": source_session_id,
                },
            )
        )

    def _build_terminal_payload(self, record: MessageRecord) -> dict[str, Any]:
        completed_at = record.completed_at or time.time()
        duration_ms = int(max(completed_at - record.created_at, 0) * 1000)
        payload = {
            "record_id": record.id,
            "agent_id": record.target_id,
            "child_session_id": record.child_session_id,
            "parent_session_id": record.parent_session_id,
            "parent_turn_id": record.parent_turn_id,
            "parent_tool_call_id": record.parent_tool_call_id,
            "status": record.status,
            "mode": record.mode,
            "depth": record.depth,
            "pingpong_count": record.pingpong_count,
            "attempt_count": record.attempt_count,
            "max_attempts": record.max_attempts,
            "timeout_seconds": record.timeout_seconds,
            "duration_ms": duration_ms,
            "result": record.result or "",
            "error": record.error or "",
            "cancelled": record.status == "cancelled",
            "timed_out": record.status == "timed_out",
        }
        return payload

    def _should_retry(
        self,
        record: MessageRecord,
        error_type: str,
        cancelled: bool,
    ) -> bool:
        if cancelled or error_type == "TurnCancelled":
            return False
        return record.attempt_count < record.max_attempts

    async def _cancel_background_tasks(self) -> None:
        for tasks in (self._timeout_tasks, self._retry_tasks):
            current = list(tasks.values())
            tasks.clear()
            for task in current:
                task.cancel()
            for task in current:
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    def _cancel_record_tasks(self, record_id: str) -> None:
        self._cancel_timeout_task(record_id)
        self._cancel_retry_task(record_id)

    def _cancel_timeout_task(self, record_id: str) -> None:
        task = self._timeout_tasks.pop(record_id, None)
        if task and task is not asyncio.current_task():
            task.cancel()

    def _cancel_retry_task(self, record_id: str) -> None:
        task = self._retry_tasks.pop(record_id, None)
        if task and task is not asyncio.current_task():
            task.cancel()
