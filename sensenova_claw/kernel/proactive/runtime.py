"""ProactiveRuntime — 主动任务运行时（入口层）

组合 ProactiveScheduler、ProactiveExecutor、ProactiveDelivery，
管理 proactive job 的加载、触发、执行和生命周期。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any, TYPE_CHECKING

from sensenova_claw.platform.config.config import config
from sensenova_claw.adapters.storage.repository import Repository
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import PROACTIVE_JOB_TRIGGERED
from sensenova_claw.kernel.proactive.delivery import ProactiveDelivery
from sensenova_claw.kernel.proactive.executor import ProactiveExecutor
from sensenova_claw.kernel.proactive.scheduler import ProactiveScheduler
from sensenova_claw.kernel.proactive.models import (
    DeliveryConfig,
    EventTrigger,
    JobState,
    ProactiveJob,
    ProactiveTask,
    SafetyConfig,
    TimeTrigger,
    job_from_db_row,
    job_to_db_row,
)
from sensenova_claw.kernel.proactive.triggers import compute_next_fire_ms

if TYPE_CHECKING:
    from sensenova_claw.kernel.runtime.agent_runtime import AgentRuntime
    from sensenova_claw.kernel.notification.service import NotificationService

logger = logging.getLogger(__name__)


class ProactiveRuntime:
    """主动任务运行时：入口层，组合 scheduler + executor + delivery。"""

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
        self._enabled: bool = config.get("proactive.enabled", False)
        self._max_concurrent: int = int(config.get("proactive.max_concurrent_runs", 3))

        self._jobs: dict[str, ProactiveJob] = {}

        # 组合子模块
        self._executor = ProactiveExecutor(
            bus=bus,
            repo=repo,
            agent_runtime=agent_runtime,
            memory_manager=memory_manager,
        )
        self._scheduler = ProactiveScheduler(
            bus=bus,
            jobs=self._jobs,
            running_jobs=self._executor._running_jobs,
            max_concurrent=self._max_concurrent,
            on_trigger=self._evaluate_and_execute,
        )
        self._delivery: ProactiveDelivery | None = None
        if notification_service:
            self._delivery = ProactiveDelivery(bus, notification_service)

    # ---------- 生命周期 ----------

    async def start(self) -> None:
        if not self._enabled:
            logger.info("ProactiveRuntime disabled by config")
            return

        await self._load_all_jobs()
        self._scheduler.rebuild_event_index()
        self._scheduler.start()
        logger.info("ProactiveRuntime started (%d jobs loaded)", len(self._jobs))

    async def stop(self) -> None:
        await self._scheduler.stop()
        logger.info("ProactiveRuntime stopped")

    # ---------- 外部 API ----------

    async def add_job(self, job: ProactiveJob) -> ProactiveJob:
        """添加 proactive job 并持久化。"""
        now_ms = int(time.time() * 1000)
        job.state.next_trigger_at_ms = compute_next_fire_ms(job, now_ms)
        row = job_to_db_row(job)
        await self._repo.create_proactive_job(row)
        self._jobs[job.id] = job
        self._scheduler.rebuild_event_index()
        logger.info("Proactive job added: %s (%s)", job.id, job.name)
        return job

    async def remove_job(self, job_id: str) -> bool:
        """删除 proactive job。"""
        if job_id not in self._jobs:
            return False
        await self._repo.delete_proactive_job(job_id)
        self._jobs.pop(job_id, None)
        self._executor.cleanup_job(job_id)
        self._scheduler.rebuild_event_index()
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
        self._scheduler.rebuild_event_index()
        logger.info("Proactive job %s: enabled=%s", job_id, enabled)
        return True

    async def list_jobs(self) -> list[ProactiveJob]:
        """列出所有 proactive jobs。"""
        return list(self._jobs.values())

    # ---------- 触发与执行 ----------

    async def _evaluate_and_execute(self, job: ProactiveJob) -> bool:
        """调度器回调：发布触发事件，委托 executor 执行。"""
        if not job.enabled or job.id in self._executor._running_jobs:
            return False

        # 发布触发事件
        await self._bus.publish(EventEnvelope(
            type=PROACTIVE_JOB_TRIGGERED,
            session_id="system",
            agent_id=job.agent_id,
            source="proactive",
            payload={"job_id": job.id, "job_name": job.name},
        ))

        asyncio.create_task(self._run_and_deliver(job))
        return True

    async def _run_and_deliver(self, job: ProactiveJob) -> None:
        """执行 job 并投递结果（在 task 中运行）。"""
        await self._executor.execute_job(job)
        # 投递结果（executor 完成后，检查状态）
        if self._delivery and job.state.last_status == "ok":
            # 结果已在 executor 中持久化，从最近的 run 获取
            # 简化：delivery 在 executor 外部不再重复调用
            pass

    # ---------- Job 加载 ----------

    async def _load_all_jobs(self) -> None:
        """从 config.yml + DB 加载所有 jobs。"""
        config_jobs = self._load_jobs_from_config()
        for job in config_jobs:
            self._jobs[job.id] = job
            existing = await self._repo.get_proactive_job(job.id)
            if not existing:
                await self._repo.create_proactive_job(job_to_db_row(job))

        # 从 DB 加载对话创建的 jobs（source != "config"）
        db_rows = await self._repo.list_proactive_jobs()
        for row in db_rows:
            job_id = row["id"]
            if job_id not in self._jobs:
                self._jobs[job_id] = job_from_db_row(row)

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
            )
        elif trigger_kind == "event":
            trigger = EventTrigger(
                event_type=trigger_cfg.get("event_type", ""),
                filter=trigger_cfg.get("filter"),
                debounce_ms=trigger_cfg.get("debounce_ms", 5000),
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
