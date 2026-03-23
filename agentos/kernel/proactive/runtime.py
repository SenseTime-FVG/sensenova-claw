"""ProactiveRuntime — 主动任务运行时

管理 proactive job 的加载、触发、执行和生命周期。
支持三种触发方式：定时(time)、事件(event)、条件(condition)。
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, TYPE_CHECKING


from agentos.platform.config.config import config
from agentos.adapters.storage.repository import Repository
from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import (
    AGENT_STEP_COMPLETED,
    PROACTIVE_CONDITION_EVALUATED,
    PROACTIVE_JOB_COMPLETED,
    PROACTIVE_JOB_FAILED,
    PROACTIVE_JOB_SKIPPED,
    PROACTIVE_JOB_STARTED,
    PROACTIVE_JOB_TRIGGERED,
)
from agentos.kernel.proactive.delivery import ProactiveDelivery
from agentos.kernel.proactive.models import (
    ConditionTrigger,
    DeliveryConfig,
    EventTrigger,
    JobState,
    ProactiveJob,
    ProactiveTask,
    SafetyConfig,
    TimeTrigger,
    job_from_db_row,
    job_to_db_row,
    parse_duration_ms,
)
from agentos.kernel.proactive.triggers import (
    build_condition_prompt,
    compute_next_fire_ms,
    is_event_match,
    parse_condition_response,
    should_debounce,
)

if TYPE_CHECKING:
    from agentos.kernel.runtime.agent_runtime import AgentRuntime
    from agentos.kernel.notification.service import NotificationService

logger = logging.getLogger(__name__)

_MAX_TIMER_DELAY_S = 60.0
_MIN_RETRIGGER_S = 2.0


class ProactiveRuntime:
    """主动任务运行时：加载、触发、执行 proactive jobs。"""

    def __init__(
        self,
        bus: PublicEventBus,
        repo: Repository,
        agent_runtime: AgentRuntime,
        notification_service: NotificationService | None = None,
        gateway: Any = None,
        memory_manager: Any = None,
    ):
        self._bus = bus
        self._repo = repo
        self._agent_runtime = agent_runtime
        self._notification_service = notification_service
        self._gateway = gateway
        self._memory_manager = memory_manager

        self._enabled: bool = config.get("proactive.enabled", False)
        self._max_concurrent: int = int(config.get("proactive.max_concurrent_runs", 3))

        self._jobs: dict[str, ProactiveJob] = {}
        self._running_jobs: set[str] = set()
        self._last_event_fires: dict[str, int] = {}
        self._watched_event_types: set[str] = set()

        self._timer_task: asyncio.Task | None = None
        self._event_task: asyncio.Task | None = None
        self._delivery: ProactiveDelivery | None = None

    # ---------- 生命周期 ----------

    async def start(self) -> None:
        if not self._enabled:
            logger.info("ProactiveRuntime disabled by config")
            return

        if self._notification_service:
            self._delivery = ProactiveDelivery(self._bus, self._notification_service)

        await self._load_all_jobs()
        self._event_task = asyncio.create_task(self._event_loop())
        self._arm_timer()
        logger.info("ProactiveRuntime started (%d jobs loaded)", len(self._jobs))

    async def stop(self) -> None:
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
            self._timer_task = None
        if self._event_task:
            self._event_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._event_task
            self._event_task = None
        logger.info("ProactiveRuntime stopped")

    # ---------- 外部 API ----------

    async def add_job(self, job: ProactiveJob) -> ProactiveJob:
        """添加 proactive job 并持久化。"""
        now_ms = int(time.time() * 1000)
        job.state.next_trigger_at_ms = compute_next_fire_ms(job, now_ms)
        row = job_to_db_row(job)
        await self._repo.create_proactive_job(row)
        self._jobs[job.id] = job
        self._rebuild_event_index()
        self._arm_timer()
        logger.info("Proactive job added: %s (%s)", job.id, job.name)
        return job

    async def remove_job(self, job_id: str) -> bool:
        """删除 proactive job。"""
        if job_id not in self._jobs:
            return False
        await self._repo.delete_proactive_job(job_id)
        self._jobs.pop(job_id, None)
        self._rebuild_event_index()
        logger.info("Proactive job removed: %s", job_id)
        return True

    async def set_job_enabled(self, job_id: str, enabled: bool) -> bool:
        """启用/禁用 proactive job。"""
        job = self._jobs.get(job_id)
        if not job:
            return False
        job.enabled = enabled
        now_ms = int(time.time() * 1000)
        if enabled:
            job.state.next_trigger_at_ms = compute_next_fire_ms(job, now_ms)
            job.state.consecutive_errors = 0
        else:
            job.state.next_trigger_at_ms = None
        await self._repo.update_proactive_job(job_id, {
            "enabled": 1 if enabled else 0,
            "state_json": json.dumps({
                "next_trigger_at_ms": job.state.next_trigger_at_ms,
                "consecutive_errors": job.state.consecutive_errors,
                "last_triggered_at_ms": job.state.last_triggered_at_ms,
                "last_completed_at_ms": job.state.last_completed_at_ms,
                "last_status": job.state.last_status,
                "total_runs": job.state.total_runs,
            }),
        })
        self._rebuild_event_index()
        if enabled:
            self._arm_timer()
        logger.info("Proactive job %s: enabled=%s", job_id, enabled)
        return True

    async def list_jobs(self) -> list[ProactiveJob]:
        """列出所有 proactive jobs。"""
        return list(self._jobs.values())

    # ---------- Job 加载 ----------

    async def _load_all_jobs(self) -> None:
        """从 config.yml + DB 加载所有 jobs。"""
        config_jobs = self._load_jobs_from_config()
        for job in config_jobs:
            self._jobs[job.id] = job
            # 同步到 DB（upsert）
            existing = await self._repo.get_proactive_job(job.id)
            if not existing:
                await self._repo.create_proactive_job(job_to_db_row(job))

        # 从 DB 加载对话创建的 jobs（source != "config"）
        db_rows = await self._repo.list_proactive_jobs()
        for row in db_rows:
            job_id = row["id"]
            if job_id not in self._jobs:
                self._jobs[job_id] = job_from_db_row(row)

        self._rebuild_event_index()
        logger.info("Loaded %d proactive jobs (%d from config)", len(self._jobs), len(config_jobs))

    def _load_jobs_from_config(self) -> list[ProactiveJob]:
        """从 config.yml 的 proactive.jobs 列表解析 job 定义。"""
        items = config.get("proactive.jobs", [])
        if not isinstance(items, list):
            return []

        jobs: list[ProactiveJob] = []
        now_ms = int(time.time() * 1000)
        for item in items:
            try:
                job = self._parse_job_config(item, now_ms)
                jobs.append(job)
            except Exception:
                logger.exception("Failed to parse proactive job: %s", item.get("name", "?"))
        return jobs

    def _parse_job_config(self, item: dict, now_ms: int) -> ProactiveJob:
        """将 config 中的单个 job 配置解析为 ProactiveJob。"""
        name = item["name"]
        job_id = f"pj_cfg_{hashlib.md5(name.encode()).hexdigest()[:12]}"

        # 解析 trigger
        trigger_cfg = item.get("trigger", {})
        trigger_kind = trigger_cfg.get("kind", "time")
        if trigger_kind == "time":
            trigger = TimeTrigger(
                cron=trigger_cfg.get("cron"),
                every=trigger_cfg.get("every"),
                condition=trigger_cfg.get("condition"),
            )
        elif trigger_kind == "event":
            trigger = EventTrigger(
                event_type=trigger_cfg.get("event_type", ""),
                filter=trigger_cfg.get("filter"),
                debounce_ms=trigger_cfg.get("debounce_ms", 5000),
                condition=trigger_cfg.get("condition"),
            )
        elif trigger_kind == "condition":
            trigger = ConditionTrigger(
                check_interval=trigger_cfg.get("check_interval", "5m"),
                condition=trigger_cfg.get("condition", ""),
            )
        else:
            raise ValueError(f"未知 trigger kind: {trigger_kind}")

        # 解析 task
        task_cfg = item.get("task", {})
        task = ProactiveTask(
            prompt=task_cfg.get("prompt", ""),
            use_memory=task_cfg.get("use_memory", False),
            system_prompt_override=task_cfg.get("system_prompt_override"),
        )

        # 解析 delivery
        delivery_cfg = item.get("delivery", {})
        delivery = DeliveryConfig(
            channels=delivery_cfg.get("channels", []),
            feishu_target=delivery_cfg.get("feishu_target"),
            summary_prompt=delivery_cfg.get("summary_prompt"),
        )

        # 解析 safety
        safety_cfg = item.get("safety", {})
        safety = SafetyConfig(
            allowed_tools=safety_cfg.get("allowed_tools"),
            blocked_tools=safety_cfg.get("blocked_tools"),
            max_tool_calls=safety_cfg.get("max_tool_calls", 20),
            max_llm_calls=safety_cfg.get("max_llm_calls", 10),
            max_duration_ms=safety_cfg.get("max_duration_ms", 300_000),
            auto_disable_after_errors=safety_cfg.get("auto_disable_after_errors", 3),
        )

        job = ProactiveJob(
            id=job_id,
            name=name,
            agent_id=item.get("agent_id", "proactive-agent"),
            enabled=item.get("enabled", True),
            trigger=trigger,
            task=task,
            delivery=delivery,
            safety=safety,
            state=JobState(next_trigger_at_ms=compute_next_fire_ms(
                ProactiveJob(trigger=trigger), now_ms,
            )),
            source="config",
        )
        return job

    def _rebuild_event_index(self) -> None:
        """重建事件类型索引，用于事件循环快速过滤。"""
        self._watched_event_types.clear()
        for job in self._jobs.values():
            if job.enabled and isinstance(job.trigger, EventTrigger):
                self._watched_event_types.add(job.trigger.event_type)

    # ---------- 定时器 ----------

    def _arm_timer(self) -> None:
        """设置定时器，延迟后触发 _on_timer。"""
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
        self._timer_task = asyncio.ensure_future(self._delayed_timer())

    async def _delayed_timer(self) -> None:
        try:
            delay = self._compute_timer_delay()
            await asyncio.sleep(delay)
            await self._on_timer()
        except asyncio.CancelledError:
            pass

    def _compute_timer_delay(self) -> float:
        """计算到最近到期 job 的延迟秒数。"""
        now_ms = int(time.time() * 1000)
        min_delay = _MAX_TIMER_DELAY_S
        for job in self._jobs.values():
            if not job.enabled or job.id in self._running_jobs:
                continue
            next_ms = job.state.next_trigger_at_ms
            if next_ms is not None:
                delay_s = max((next_ms - now_ms) / 1000.0, _MIN_RETRIGGER_S)
                min_delay = min(min_delay, delay_s)
        return min_delay

    async def _on_timer(self) -> None:
        """定时器回调：扫描到期的 time/condition jobs 并触发。"""
        try:
            now_ms = int(time.time() * 1000)
            for job in list(self._jobs.values()):
                if not job.enabled or job.id in self._running_jobs:
                    continue
                if not isinstance(job.trigger, (TimeTrigger, ConditionTrigger)):
                    continue
                next_ms = job.state.next_trigger_at_ms
                if next_ms is not None and next_ms <= now_ms:
                    if len(self._running_jobs) >= self._max_concurrent:
                        break
                    await self._evaluate_and_execute(job)
        except Exception:
            logger.exception("ProactiveRuntime._on_timer error")
        finally:
            if self._enabled:
                self._arm_timer()

    # ---------- 事件循环 ----------

    async def _event_loop(self) -> None:
        """订阅 PublicEventBus，监听事件触发型 jobs。"""
        try:
            async for event in self._bus.subscribe():
                try:
                    if event.type not in self._watched_event_types:
                        continue
                    for job in list(self._jobs.values()):
                        if not job.enabled or job.id in self._running_jobs:
                            continue
                        if not isinstance(job.trigger, EventTrigger):
                            continue
                        if not is_event_match(job.trigger, event.type, event.payload):
                            continue
                        if should_debounce(job.id, job.trigger.debounce_ms, self._last_event_fires):
                            continue
                        self._last_event_fires[job.id] = int(time.time() * 1000)
                        if len(self._running_jobs) >= self._max_concurrent:
                            logger.warning("达到最大并发数，跳过事件触发: %s", job.id)
                            continue
                        await self._evaluate_and_execute(job)
                except Exception:
                    logger.exception("ProactiveRuntime event_loop handler error")
        except asyncio.CancelledError:
            pass

    # ---------- 评估与执行 ----------

    async def _evaluate_and_execute(self, job: ProactiveJob) -> bool:
        """评估条件并决定是否执行 job。返回是否启动了执行。"""
        if not job.enabled or job.id in self._running_jobs:
            return False

        # 发布触发事件
        await self._bus.publish(EventEnvelope(
            type=PROACTIVE_JOB_TRIGGERED,
            session_id="system",
            agent_id=job.agent_id,
            source="proactive",
            payload={"job_id": job.id, "job_name": job.name},
        ))

        # 获取条件文本
        condition = self._get_condition(job)

        if condition:
            met = await self._evaluate_condition(condition)
            await self._bus.publish(EventEnvelope(
                type=PROACTIVE_CONDITION_EVALUATED,
                session_id="system",
                agent_id=job.agent_id,
                source="proactive",
                payload={"job_id": job.id, "condition": condition, "met": met},
            ))
            if not met:
                now_ms = int(time.time() * 1000)
                job.state.next_trigger_at_ms = compute_next_fire_ms(job, now_ms)
                await self._bus.publish(EventEnvelope(
                    type=PROACTIVE_JOB_SKIPPED,
                    session_id="system",
                    agent_id=job.agent_id,
                    source="proactive",
                    payload={"job_id": job.id, "reason": "condition_not_met"},
                ))
                return False

        asyncio.create_task(self._execute_job(job))
        return True

    def _get_condition(self, job: ProactiveJob) -> str | None:
        """从 trigger 中提取条件文本。"""
        trigger = job.trigger
        if isinstance(trigger, ConditionTrigger):
            return trigger.condition
        if isinstance(trigger, (TimeTrigger, EventTrigger)):
            return trigger.condition
        return None

    async def _evaluate_condition(self, condition: str) -> bool:
        """通过 LLM 评估条件。LLM 不可用时降级为 True。"""
        try:
            from agentos.adapters.llm.factory import create_llm_provider
            prompt = build_condition_prompt(condition)
            provider = create_llm_provider()
            response = await provider.chat([{"role": "user", "content": prompt}])
            result_text = response.get("content", "")
            return parse_condition_response(result_text)
        except Exception:
            logger.warning("条件评估 LLM 调用失败，降级为 True: %s", condition)
            return True

    async def _execute_job(self, job: ProactiveJob) -> None:
        """执行单个 proactive job：创建隔离 session，等待完成，投递结果。"""
        session_id = f"proactive_{job.id}_{uuid.uuid4().hex[:8]}"
        run_id = f"pr_{uuid.uuid4().hex[:12]}"
        start_ms = int(time.time() * 1000)

        self._running_jobs.add(job.id)
        job.state.last_triggered_at_ms = start_ms
        job.state.last_status = "running"

        # 创建 proactive_run 记录
        await self._repo.create_proactive_run({
            "id": run_id,
            "job_id": job.id,
            "session_id": session_id,
            "status": "running",
            "triggered_by": job.trigger.kind,
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
            result_text = await self._wait_for_completion(session_id, timeout_ms / 1000.0)

            # 成功
            end_ms = int(time.time() * 1000)
            job.state.last_completed_at_ms = end_ms
            job.state.last_status = "ok"
            job.state.consecutive_errors = 0
            job.state.total_runs += 1
            now_ms = int(time.time() * 1000)
            job.state.next_trigger_at_ms = compute_next_fire_ms(job, now_ms)

            await self._repo.update_proactive_run(run_id, {
                "status": "ok",
                "completed_at_ms": end_ms,
                "result_summary": result_text[:500] if result_text else "",
            })

            await self._bus.publish(EventEnvelope(
                type=PROACTIVE_JOB_COMPLETED,
                session_id=session_id,
                agent_id=job.agent_id,
                source="proactive",
                payload={
                    "job_id": job.id,
                    "run_id": run_id,
                    "result": result_text[:500] if result_text else "",
                },
            ))

            # 投递结果
            if self._delivery and result_text:
                await self._delivery.deliver(job, session_id, result_text)

        except Exception as exc:
            end_ms = int(time.time() * 1000)
            await self._handle_failure(job, run_id, session_id, str(exc)[:500], end_ms)

        finally:
            self._running_jobs.discard(job.id)
            # 持久化 state
            await self._persist_job_state(job)

    async def _handle_failure(
        self, job: ProactiveJob, run_id: str, session_id: str, error: str, end_ms: int,
    ) -> None:
        """处理 job 执行失败：更新状态，自动禁用。"""
        job.state.consecutive_errors += 1
        job.state.last_status = "error"
        job.state.last_completed_at_ms = end_ms
        now_ms = int(time.time() * 1000)
        job.state.next_trigger_at_ms = compute_next_fire_ms(job, now_ms)

        await self._repo.update_proactive_run(run_id, {
            "status": "error",
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
            self._rebuild_event_index()

        logger.error("Proactive job %s failed: %s", job.id, error)

    # ---------- 辅助方法 ----------

    def _build_prompt(self, job: ProactiveJob) -> str:
        """构建 agent session 的 prompt。"""
        parts = [job.task.prompt]
        if job.task.use_memory and self._memory_manager:
            try:
                memory_ctx = self._memory_manager.get_context(job.agent_id)
                if memory_ctx:
                    parts.append(f"\n\n## 记忆上下文\n{memory_ctx}")
            except Exception:
                logger.warning("获取记忆上下文失败: job=%s", job.id)
        return "\n".join(parts)

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

    async def _wait_for_completion(self, session_id: str, timeout: float = 300) -> str:
        """订阅 PublicEventBus 等待 AGENT_STEP_COMPLETED。"""
        queue: asyncio.Queue[EventEnvelope] = asyncio.Queue()
        self._bus._subscribers.add(queue)
        try:
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise asyncio.TimeoutError(f"Proactive session 超时: {session_id}")
                event = await asyncio.wait_for(queue.get(), timeout=remaining)
                if event.type == AGENT_STEP_COMPLETED and event.session_id == session_id:
                    return event.payload.get("result", {}).get("content", "")
        finally:
            self._bus._subscribers.discard(queue)

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
