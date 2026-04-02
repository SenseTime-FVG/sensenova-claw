"""ProactiveExecutor — job 执行器

负责单个 proactive job 的执行生命周期：
- 并发锁保护（同一 job 不重复执行）
- 创建隔离 session，构建 prompt，等待完成
- 超时检测（含心跳超时）
- 失败处理与自动禁用
- 状态持久化
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, TYPE_CHECKING

from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import (
    AGENT_STEP_COMPLETED,
    PROACTIVE_JOB_COMPLETED,
    PROACTIVE_JOB_FAILED,
    PROACTIVE_JOB_STARTED,
)
from sensenova_claw.kernel.proactive.models import ProactiveJob
from sensenova_claw.kernel.proactive.triggers import compute_next_fire_ms

if TYPE_CHECKING:
    from sensenova_claw.adapters.storage.repository import Repository
    from sensenova_claw.kernel.events.bus import PublicEventBus
    from sensenova_claw.kernel.runtime.agent_runtime import AgentRuntime

logger = logging.getLogger(__name__)


class ProactiveExecutor:
    """执行单个 proactive job，提供并发锁和超时保护。"""

    def __init__(
        self,
        bus: PublicEventBus,
        repo: Repository,
        agent_runtime: AgentRuntime,
        memory_manager: Any | None,
    ):
        self._bus = bus
        self._repo = repo
        self._agent_runtime = agent_runtime
        self._memory_manager = memory_manager

        # 每个 job_id 对应一把锁，防止同一 job 并发执行
        self._job_locks: dict[str, asyncio.Lock] = {}
        # 当前正在执行的 job id 集合
        self._running_jobs: set[str] = set()

    async def execute_job(self, job: ProactiveJob, trigger_event: EventEnvelope | None = None) -> tuple[str, str | None]:
        """执行 job，返回 (session_id, result_text)。若跳过或失败返回 ("", None)。"""
        if job.id in self._running_jobs:
            logger.debug("Proactive job %s 已在运行，跳过", job.id)
            return ("", None)
        if job.id not in self._job_locks:
            self._job_locks[job.id] = asyncio.Lock()
        lock = self._job_locks[job.id]

        # 尝试获取锁（非阻塞）
        if not lock.locked():
            async with lock:
                return await self._do_execute(job, trigger_event)
        else:
            logger.debug("Proactive job %s 锁已被占用，跳过", job.id)
            return ("", None)

    def cleanup_job(self, job_id: str) -> None:
        """删除 job 时清理对应的锁资源。"""
        self._job_locks.pop(job_id, None)
        self._running_jobs.discard(job_id)

    async def _do_execute(self, job: ProactiveJob, trigger_event: EventEnvelope | None = None) -> tuple[str, str | None]:
        # 推荐模式：在隐藏 scratch session 中生成推荐，避免污染原会话历史
        if trigger_event and job.delivery.recommendation_type:
            return await self._do_execute_recommendation_scratch(job, trigger_event)

        # 独立会话模式（现有逻辑不变）
        session_id = self._build_session_id(job)
        run_id = f"pr_{uuid.uuid4().hex[:12]}"
        start_ms = int(time.time() * 1000)
        result_text: str | None = None
        self._running_jobs.add(job.id)
        job.state.last_triggered_at_ms = start_ms
        job.state.last_status = "running"

        # 创建 proactive_run 记录
        await self._repo.create_proactive_run({
            "id": run_id,
            "job_id": job.id,
            "session_id": session_id,
            "status": "running",
            "triggered_by": job.trigger.kind if job.trigger else "manual",
            "started_at_ms": start_ms,
        })

        await self._bus.publish(EventEnvelope(
            type=PROACTIVE_JOB_STARTED,
            session_id=session_id,
            agent_id=job.agent_id,
            source="proactive",
            payload={"job_id": job.id, "run_id": run_id, "session_id": session_id},
        ))

        try:
            prompt = self._build_prompt(job)
            meta = self._build_session_meta(job)

            await self._agent_runtime.spawn_agent_session(
                agent_id=job.agent_id,
                session_id=session_id,
                user_input=prompt,
                meta=meta,
            )

            timeout_ms = job.safety.max_duration_ms
            result_text = await self._wait_for_completion(session_id, timeout_ms)

            if result_text is None:
                # 超时路径
                end_ms = int(time.time() * 1000)
                await self._handle_failure(
                    job, run_id, session_id,
                    f"执行超时（{timeout_ms}ms）", end_ms,
                    status="timeout",
                )
                return (session_id, None)
            end_ms = int(time.time() * 1000)
            job.state.last_completed_at_ms = end_ms
            job.state.last_status = "ok"
            job.state.consecutive_errors = 0
            job.state.total_runs += 1
            job.state.next_trigger_at_ms = compute_next_fire_ms(job, end_ms)

            await self._repo.update_proactive_run(run_id, {
                "status": "ok", "completed_at_ms": end_ms,
                "result_summary": result_text or "",
            })

            await self._bus.publish(EventEnvelope(
                type=PROACTIVE_JOB_COMPLETED, session_id=session_id,
                agent_id=job.agent_id, source="proactive",
                payload={"job_id": job.id, "run_id": run_id,
                         "result": result_text or ""},
            ))

        except Exception as exc:
            end_ms = int(time.time() * 1000)
            await self._handle_failure(job, run_id, session_id, str(exc)[:500], end_ms)
            return (session_id, None)
        finally:
            self._running_jobs.discard(job.id)
            await self._persist_job_state(job)
        return (session_id, result_text)

    async def _do_execute_recommendation_scratch(
        self,
        job: ProactiveJob,
        trigger_event: EventEnvelope,
    ) -> tuple[str, str | None]:
        """推荐模式：在隐藏 scratch session 中生成推荐结果。"""
        source_session_id = trigger_event.session_id
        scratch_session_id = self._build_session_id(job)
        run_id = f"pr_{uuid.uuid4().hex[:12]}"
        start_ms = int(time.time() * 1000)
        result_text: str | None = None
        self._running_jobs.add(job.id)
        job.state.last_triggered_at_ms = start_ms
        job.state.last_status = "running"

        await self._repo.create_proactive_run({
            "id": run_id, "job_id": job.id,
            "session_id": scratch_session_id,
            "status": "running", "triggered_by": "event",
            "started_at_ms": start_ms,
        })

        try:
            prompt = await self._build_recommendation_prompt(job, source_session_id)
            meta = self._build_recommendation_scratch_meta(job, source_session_id)

            await self._agent_runtime.spawn_agent_session(
                agent_id=job.agent_id,
                session_id=scratch_session_id,
                user_input=prompt,
                parent_session_id=source_session_id,
                meta=meta,
            )

            timeout_ms = job.safety.max_duration_ms
            result_text = await self._wait_for_completion(scratch_session_id, timeout_ms)

            if result_text is None:
                end_ms = int(time.time() * 1000)
                await self._handle_failure(
                    job, run_id, scratch_session_id,
                    f"执行超时（{timeout_ms}ms）", end_ms, status="timeout",
                )
                return (scratch_session_id, None)

            end_ms = int(time.time() * 1000)
            job.state.last_status = "ok"
            job.state.last_completed_at_ms = end_ms
            job.state.consecutive_errors = 0
            job.state.total_runs += 1
            await self._repo.update_proactive_run(run_id, {
                "status": "ok",
                "completed_at_ms": end_ms,
                "result_summary": result_text,
            })
            await self._bus.publish(EventEnvelope(
                type=PROACTIVE_JOB_COMPLETED,
                session_id=scratch_session_id,
                agent_id=job.agent_id,
                source="proactive",
                payload={"job_id": job.id, "run_id": run_id, "result": result_text},
            ))
            await self._persist_job_state(job)
            return (scratch_session_id, result_text)

        except Exception as e:
            end_ms = int(time.time() * 1000)
            await self._handle_failure(job, run_id, scratch_session_id, str(e), end_ms)
            return (scratch_session_id, None)
        finally:
            self._running_jobs.discard(job.id)

    async def _wait_for_completion_by_turn(
        self, session_id: str, turn_id: str, timeout_ms: float,
    ) -> str | None:
        """等待指定 turn 的 agent.step_completed 事件。"""
        timeout_s = timeout_ms / 1000.0
        heartbeat_timeout_s = timeout_s / 3.0
        queue = self._bus.subscribe_queue()
        try:
            deadline = time.monotonic() + timeout_s
            last_event_time = time.monotonic()

            while True:
                now = time.monotonic()
                remaining = deadline - now
                if remaining <= 0:
                    return None

                # 心跳超时：长时间无任何事件
                if (now - last_event_time) >= heartbeat_timeout_s:
                    logger.warning(
                        "推荐 turn %s 心跳超时（%.1fs 无事件）",
                        turn_id, heartbeat_timeout_s,
                    )
                    return None

                # 等待下一个事件，最多等到心跳超时
                wait_s = min(remaining, heartbeat_timeout_s - (now - last_event_time))
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=max(wait_s, 0.01))
                except asyncio.TimeoutError:
                    continue

                last_event_time = time.monotonic()

                if (event.type == AGENT_STEP_COMPLETED
                        and event.session_id == session_id
                        and event.turn_id == turn_id):
                    return event.payload.get("result", {}).get("content", "")
        finally:
            self._bus.unsubscribe_queue(queue)

    async def _handle_failure(
        self,
        job: ProactiveJob,
        run_id: str,
        session_id: str,
        error: str,
        end_ms: int,
        status: str = "error",
    ) -> None:
        """处理 job 执行失败：更新状态，自动禁用。"""
        job.state.consecutive_errors += 1
        job.state.last_status = status
        job.state.last_completed_at_ms = end_ms
        job.state.next_trigger_at_ms = compute_next_fire_ms(job, end_ms)

        await self._repo.update_proactive_run(run_id, {
            "status": status,
            "completed_at_ms": end_ms,
            "error_message": error,
        })

        await self._bus.publish(EventEnvelope(
            type=PROACTIVE_JOB_FAILED,
            session_id=session_id,
            agent_id=job.agent_id,
            source="proactive",
            payload={"job_id": job.id, "run_id": run_id, "error": error},
        ))

        # 连续失败超过阈值，自动禁用
        threshold = job.safety.auto_disable_after_errors
        if job.state.consecutive_errors >= threshold:
            logger.warning(
                "Proactive job %s 连续失败 %d 次，自动禁用",
                job.id, job.state.consecutive_errors,
            )
            job.enabled = False
            job.state.next_trigger_at_ms = None
            await self._repo.update_proactive_job(job.id, {"enabled": 0})

        logger.error("Proactive job %s failed (%s): %s", job.id, status, error)

    def _build_prompt(self, job: ProactiveJob) -> str:
        """构建 agent session 的 prompt，可选拼接记忆上下文。"""
        parts = [job.task.prompt]
        if job.task.use_memory and self._memory_manager:
            try:
                memory_ctx = self._memory_manager.get_context(job.agent_id)
                if memory_ctx:
                    parts.append(f"\n\n## 记忆上下文\n{memory_ctx}")
            except Exception:
                logger.warning("获取记忆上下文失败: job=%s", job.id)
        return "\n".join(parts)

    async def _build_recommendation_prompt(self, job: ProactiveJob, source_session_id: str) -> str:
        """基于原会话完整历史快照构建推荐 prompt。"""
        history = await self._repo.get_session_messages(source_session_id)
        if history:
            history = await self._compress_source_history_if_needed(source_session_id, history)
        history_snapshot = self._format_history_snapshot(history)
        task_prompt = self._build_prompt(job)

        return "\n".join([
            "你正在为一个真实用户会话生成“下一问推荐”。",
            "不要把自己当作用户继续对话，也不要回答原问题。",
            f"源会话 ID: {source_session_id}",
            "",
            "## 源会话完整历史快照",
            history_snapshot,
            "",
            "## 当前任务",
            task_prompt,
        ])

    async def _compress_source_history_if_needed(
        self,
        source_session_id: str,
        history: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """优先复用现有上下文压缩器，避免超长历史直接塞给推荐 scratch session。"""
        compressor = getattr(self._agent_runtime, "context_compressor", None)
        if not compressor:
            return history

        source_meta = await self._repo.get_session_meta(source_session_id) or {}
        source_agent_id = str(source_meta.get("agent_id") or "default")
        try:
            return await compressor.compress_if_needed(
                source_session_id,
                history,
                agent_id=source_agent_id,
            )
        except Exception:
            logger.warning("压缩推荐来源会话历史失败，回退到原始历史: session=%s", source_session_id, exc_info=True)
            return history

    def _format_history_snapshot(self, history: list[dict[str, Any]]) -> str:
        """将消息历史转成适合推荐 agent 消费的文本快照。"""
        if not history:
            return "（该会话暂无历史消息）"

        role_map = {
            "user": "用户",
            "assistant": "助手",
            "tool": "工具",
            "system": "系统",
        }
        lines: list[str] = []
        for index, message in enumerate(history, start=1):
            role = role_map.get(str(message.get("role", "")).lower(), str(message.get("role", "unknown")))
            content = str(message.get("content") or "").strip()
            if not content:
                content = "（空内容）"
            lines.append(f"{index}. {role}: {content}")

            tool_calls = message.get("tool_calls")
            if tool_calls:
                lines.append(
                    f"   tool_calls: {json.dumps(tool_calls, ensure_ascii=False)}"
                )

            if message.get("role") == "tool":
                tool_name = str(message.get("name") or message.get("tool_name") or "").strip()
                if tool_name:
                    lines.append(f"   tool_name: {tool_name}")
                tool_call_id = str(message.get("tool_call_id") or "").strip()
                if tool_call_id:
                    lines.append(f"   tool_call_id: {tool_call_id}")
        return "\n".join(lines)

    def _build_session_id(self, job: ProactiveJob) -> str:
        return f"proactive_{job.id}_{uuid.uuid4().hex[:8]}"

    def _build_session_meta(self, job: ProactiveJob) -> dict[str, Any]:
        """构建 spawn_agent_session 的 meta 参数，注入安全约束。"""
        meta: dict[str, Any] = {
            "agent_id": job.agent_id,
            "type": "proactive",
            "proactive_job_id": job.id,
        }
        safety = job.safety
        if safety.allowed_tools is not None:
            meta["allowed_tools"] = safety.allowed_tools
        if safety.blocked_tools is not None:
            meta["blocked_tools"] = safety.blocked_tools
        meta["max_tool_calls"] = safety.max_tool_calls
        meta["max_llm_calls"] = safety.max_llm_calls
        meta["max_duration_ms"] = safety.max_duration_ms
        if job.task.system_prompt_override:
            meta["system_prompt_override"] = job.task.system_prompt_override
        return meta

    def _build_recommendation_scratch_meta(
        self,
        job: ProactiveJob,
        source_session_id: str,
    ) -> dict[str, Any]:
        """构建推荐 scratch session 的 meta。"""
        meta = self._build_session_meta(job)
        meta["type"] = "proactive_recommendation_scratch"
        meta["visibility"] = "hidden"
        meta["parent_session_id"] = source_session_id
        meta["source_session_id"] = source_session_id
        return meta

    async def _wait_for_completion(
        self, session_id: str, timeout_ms: float
    ) -> str | None:
        """订阅 PublicEventBus 等待 AGENT_STEP_COMPLETED。

        返回结果文本，超时返回 None。
        含心跳超时检测：若 timeout_ms/3 内无任何事件，提前返回 None。
        """
        timeout_s = timeout_ms / 1000.0
        heartbeat_timeout_s = timeout_s / 3.0
        queue = self._bus.subscribe_queue()
        try:
            deadline = time.monotonic() + timeout_s
            last_event_time = time.monotonic()

            while True:
                now = time.monotonic()
                remaining = deadline - now
                if remaining <= 0:
                    return None

                # 心跳超时：长时间无任何事件
                if (now - last_event_time) >= heartbeat_timeout_s:
                    logger.warning(
                        "Proactive session %s 心跳超时（%.1fs 无事件）",
                        session_id, heartbeat_timeout_s,
                    )
                    return None

                # 等待下一个事件，最多等到心跳超时
                wait_s = min(remaining, heartbeat_timeout_s - (now - last_event_time))
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=max(wait_s, 0.01))
                except asyncio.TimeoutError:
                    # 可能是心跳超时，循环顶部会判断
                    continue

                last_event_time = time.monotonic()

                if event.type == AGENT_STEP_COMPLETED and event.session_id == session_id:
                    return event.payload.get("result", {}).get("content", "")
        finally:
            self._bus.unsubscribe_queue(queue)

    async def _persist_job_state(self, job: ProactiveJob) -> None:
        """将 job 的运行时状态持久化到 DB。"""
        state_json = json.dumps({
            "last_triggered_at_ms": job.state.last_triggered_at_ms,
            "last_completed_at_ms": job.state.last_completed_at_ms,
            "last_status": job.state.last_status,
            "consecutive_errors": job.state.consecutive_errors,
            "total_runs": job.state.total_runs,
            "next_trigger_at_ms": job.state.next_trigger_at_ms,
        })
        await self._repo.update_proactive_job(job.id, {"state_json": state_json})
