"""CronRuntime — 定时任务调度器

Timer 驱动，周期扫描到期 Job 并执行。Phase 1 仅支持 main session systemEvent。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from agentos.platform.config.config import config
from agentos.kernel.scheduler.models import (
    AtSchedule,
    CronDelivery,
    CronJob,
    cron_job_from_db_row,
    cron_job_to_db_row,
)
from agentos.kernel.scheduler.scheduler import compute_initial_next_run_ms, compute_next_run_at_ms
from agentos.adapters.storage.repository import Repository
from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import (
    CRON_DELIVERY_REQUESTED,
    CRON_JOB_ADDED,
    CRON_JOB_FINISHED,
    CRON_JOB_REMOVED,
    CRON_JOB_STARTED,
    CRON_SYSTEM_EVENT,
    HEARTBEAT_WAKE_REQUESTED,
)

if TYPE_CHECKING:
    from agentos.interfaces.ws.gateway import Gateway

logger = logging.getLogger(__name__)

_MAX_DELAY_S = 60.0
_MIN_RETRIGGER_S = 2.0


class CronRuntime:
    """定时任务调度器"""

    def __init__(self, bus: PublicEventBus, repo: Repository, gateway: Gateway | None = None):
        self._bus = bus
        self._repo = repo
        self._gateway = gateway
        self._running = False
        self._timer_task: asyncio.Task | None = None
        self._enabled = config.get("cron.enabled", True)

    async def start(self) -> None:
        if not self._enabled:
            logger.info("CronRuntime disabled by config")
            return
        # 启动时清除残留 running 标记
        await self._repo.clear_stale_cron_running()
        self._arm_timer()
        logger.info("CronRuntime started")

    async def stop(self) -> None:
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
            self._timer_task = None
        logger.info("CronRuntime stopped")

    # ---------- CRUD ----------

    async def add_job(self, job: CronJob) -> CronJob:
        """添加定时任务"""
        now_ms = int(time.time() * 1000)
        job.state.next_run_at_ms = compute_initial_next_run_ms(job, now_ms)
        # at 类型默认自动删除
        if isinstance(job.schedule, AtSchedule) and job.delete_after_run is None:
            job.delete_after_run = True
        row = cron_job_to_db_row(job)
        await self._repo.create_cron_job(row)
        await self._bus.publish(EventEnvelope(
            type=CRON_JOB_ADDED, session_id="system", source="cron",
            payload={"job_id": job.id, "name": job.name},
        ))
        self._arm_timer()
        logger.info("Cron job added: %s (next=%s)", job.id, job.state.next_run_at_ms)
        return job

    async def list_jobs(self) -> list[CronJob]:
        """列出所有定时任务"""
        rows = await self._repo.list_cron_jobs()
        return [cron_job_from_db_row(r) for r in rows]

    async def remove_job(self, job_id: str) -> bool:
        """删除定时任务"""
        existing = await self._repo.get_cron_job(job_id)
        if not existing:
            return False
        await self._repo.delete_cron_job(job_id)
        await self._bus.publish(EventEnvelope(
            type=CRON_JOB_REMOVED, session_id="system", source="cron",
            payload={"job_id": job_id},
        ))
        logger.info("Cron job removed: %s", job_id)
        return True

    # ---------- Session → Delivery 解析 ----------

    def resolve_delivery_for_session(self, session_id: str) -> CronDelivery | None:
        """根据调用方 session_id 解析投递配置，持久化到 CronJob.delivery"""
        if not self._gateway or not session_id:
            return None
        channel_id = self._gateway._session_bindings.get(session_id)
        if not channel_id:
            return None

        delivery = CronDelivery(mode="announce", channel_id=channel_id)

        # 飞书渠道：从 session_meta 取出 chat_id 作为投递目标
        channel = self._gateway._channels.get(channel_id)
        if channel and hasattr(channel, "_session_meta"):
            lock = getattr(channel, "_lock", None)
            if lock and hasattr(lock, "__enter__"):
                with lock:
                    meta = channel._session_meta.get(session_id)
            else:
                meta = channel._session_meta.get(session_id)
            if meta and hasattr(meta, "chat_id"):
                delivery.to = meta.chat_id

        logger.debug(
            "Resolved delivery for session %s: channel=%s to=%s",
            session_id, delivery.channel_id, delivery.to,
        )
        return delivery

    # ---------- Timer ----------

    def _arm_timer(self) -> None:
        """设置定时器，延迟后触发 _on_timer"""
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
        self._timer_task = asyncio.ensure_future(self._delayed_timer())

    async def _delayed_timer(self) -> None:
        """等待延迟后执行 _on_timer"""
        try:
            # 计算最近到期 job 的延迟
            delay = await self._compute_delay()
            await asyncio.sleep(delay)
            await self._on_timer()
        except asyncio.CancelledError:
            pass

    async def _compute_delay(self) -> float:
        """计算到最近到期 job 的延迟秒数"""
        rows = await self._repo.list_cron_jobs(enabled_only=True)
        now_ms = int(time.time() * 1000)
        min_delay = _MAX_DELAY_S
        for row in rows:
            next_ms = row.get("next_run_at_ms")
            if next_ms is not None and row.get("running_at_ms") is None:
                delay_s = max((next_ms - now_ms) / 1000.0, _MIN_RETRIGGER_S)
                min_delay = min(min_delay, delay_s)
        return min_delay

    async def _on_timer(self) -> None:
        """定时器回调：扫描并执行到期 Job"""
        if self._running:
            self._arm_timer()
            return

        self._running = True
        try:
            now_ms = int(time.time() * 1000)
            rows = await self._repo.get_runnable_cron_jobs(now_ms)
            if not rows:
                return

            max_concurrent = int(config.get("cron.max_concurrent_runs", 1))
            for row in rows[:max_concurrent]:
                job = cron_job_from_db_row(row)
                await self._execute_job(job, now_ms)
        except Exception:
            logger.exception("CronRuntime._on_timer error")
        finally:
            self._running = False
            self._arm_timer()

    # ---------- 执行 ----------

    async def _execute_job(self, job: CronJob, now_ms: int) -> None:
        """执行单个 Job"""
        start_ms = int(time.time() * 1000)

        # 标记 running
        await self._repo.update_cron_job_state(job.id, {"running_at_ms": start_ms})

        run_id = await self._repo.insert_cron_run({
            "job_id": job.id,
            "started_at_ms": start_ms,
            "status": "running",
            "created_at": time.time(),
        })

        await self._bus.publish(EventEnvelope(
            type=CRON_JOB_STARTED, session_id="system", source="cron",
            payload={"job_id": job.id, "run_id": run_id},
        ))

        try:
            if job.session_target == "main":
                await self._execute_main_session(job)
            else:
                logger.warning("Isolated session 尚未实现 (Phase 2)，跳过 job %s", job.id)
                raise NotImplementedError("Isolated session not yet supported")

            # 成功
            end_ms = int(time.time() * 1000)
            duration = end_ms - start_ms
            next_run = compute_next_run_at_ms(job, end_ms)

            await self._repo.update_cron_job_state(job.id, {
                "running_at_ms": None,
                "last_run_at_ms": end_ms,
                "last_run_status": "ok",
                "last_error": None,
                "last_duration_ms": duration,
                "consecutive_errors": 0,
                "next_run_at_ms": next_run,
            })
            await self._repo.update_cron_run(run_id, {
                "ended_at_ms": end_ms,
                "status": "ok",
                "duration_ms": duration,
            })

            # at 类型成功后自动删除
            if job.delete_after_run:
                await self._repo.delete_cron_job(job.id)
                logger.info("Auto-deleted at-type job %s", job.id)

        except Exception as exc:
            end_ms = int(time.time() * 1000)
            await self._repo.update_cron_job_state(job.id, {
                "running_at_ms": None,
                "last_run_at_ms": end_ms,
                "last_run_status": "error",
                "last_error": str(exc)[:500],
                "last_duration_ms": end_ms - start_ms,
                "consecutive_errors": job.state.consecutive_errors + 1,
                "next_run_at_ms": compute_next_run_at_ms(job, end_ms),
            })
            await self._repo.update_cron_run(run_id, {
                "ended_at_ms": end_ms,
                "status": "error",
                "error": str(exc)[:500],
                "duration_ms": end_ms - start_ms,
            })
            logger.error("Job %s failed: %s", job.id, exc)

        await self._bus.publish(EventEnvelope(
            type=CRON_JOB_FINISHED, session_id="system", source="cron",
            payload={"job_id": job.id, "run_id": run_id},
        ))

    async def _execute_main_session(self, job: CronJob) -> None:
        """主会话执行：发布 system event + 直接投递到 channels + 可选触发 heartbeat"""
        text = ""
        if hasattr(job.payload, "text"):
            text = job.payload.text

        # 发布 cron.system_event（供 HeartbeatRuntime 积累 pending events）
        await self._bus.publish(EventEnvelope(
            type=CRON_SYSTEM_EVENT,
            session_id="system",
            source="cron",
            payload={"job_id": job.id, "text": text},
        ))

        # 直接投递文本到 channels（不依赖 HeartbeatRuntime）
        if text and self._gateway:
            await self._deliver_text(job, text)

        # wake_mode=="now" 时触发 heartbeat（如果 HeartbeatRuntime 启用则会处理）
        if job.wake_mode == "now":
            await self._bus.publish(EventEnvelope(
                type=HEARTBEAT_WAKE_REQUESTED,
                session_id="system",
                source="cron",
                payload={"reason": f"cron_job:{job.id}", "text": text},
            ))

    async def _deliver_text(self, job: CronJob, text: str) -> None:
        """将 cron 文本直接投递到目标 channels"""
        delivery = job.delivery
        if delivery and delivery.mode == "none":
            return

        if delivery and delivery.channel_id:
            channel_ids = [delivery.channel_id]
        else:
            channel_ids = list(self._gateway._channels.keys())

        to = delivery.to if delivery else None

        for channel_id in channel_ids:
            # 优先使用 send_outbound 直接调 API（飞书等 OutboundCapable channel）
            if to:
                result = await self._gateway.send_outbound(channel_id, to, text)
                if result.get("success"):
                    logger.info("Cron text sent via outbound to %s:%s", channel_id, to)
                    continue
                logger.debug(
                    "send_outbound not available for %s, falling back: %s",
                    channel_id, result,
                )

            # 回退到 deliver_to_channel（WebSocket 广播等）
            event = EventEnvelope(
                type=CRON_DELIVERY_REQUESTED,
                session_id="system",
                source="cron",
                payload={
                    "job_id": job.id,
                    "job_name": job.name,
                    "text": text,
                    "to": to,
                },
            )
            ok = await self._gateway.deliver_to_channel(event, channel_id)
            if ok:
                logger.info("Cron text delivered to channel %s via event", channel_id)
            else:
                logger.warning("Cron text delivery failed for channel %s", channel_id)
