"""ProactiveScheduler — 触发调度器

负责定时触发和事件触发的调度评估，不执行 job 本身。
当 job 应触发时，调用 on_trigger 回调。
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Callable, Awaitable

from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.proactive.models import (
    EventTrigger,
    ProactiveJob,
    TimeTrigger,
)
from sensenova_claw.kernel.proactive.triggers import is_event_match, should_debounce

logger = logging.getLogger(__name__)

_MAX_TIMER_DELAY_S = 60.0
_MIN_RETRIGGER_S = 2.0
# debounce 字典清理阈值：超过 1 小时的条目视为过期
_DEBOUNCE_EXPIRE_MS = 3_600_000


class ProactiveScheduler:
    """调度器：管理定时器和事件监听，到期时调用 on_trigger 回调。"""

    def __init__(
        self,
        bus: PublicEventBus,
        jobs: dict[str, ProactiveJob],
        running_jobs: set[str],
        max_concurrent: int,
        on_trigger: Callable[[ProactiveJob], Awaitable[bool]],
    ) -> None:
        self._bus = bus
        self._jobs = jobs
        self._running_jobs = running_jobs
        self._max_concurrent = max_concurrent
        self._on_trigger = on_trigger

        self._last_event_fires: dict[str, int] = {}
        self._watched_event_types: set[str] = set()

        self._timer_task: asyncio.Task | None = None
        self._event_task: asyncio.Task | None = None

    # ---------- 生命周期 ----------

    def start(self) -> None:
        """启动事件循环和定时器。"""
        self._event_task = asyncio.ensure_future(self._event_loop())
        self._arm_timer()
        logger.debug("ProactiveScheduler started")

    async def stop(self) -> None:
        """停止事件循环和定时器。"""
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
            self._timer_task = None
        if self._event_task:
            self._event_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._event_task
            self._event_task = None
        logger.debug("ProactiveScheduler stopped")

    # ---------- 事件索引 ----------

    def rebuild_event_index(self) -> None:
        """重建事件类型索引，用于事件循环快速过滤。"""
        self._watched_event_types.clear()
        for job in self._jobs.values():
            if job.enabled and isinstance(job.trigger, EventTrigger):
                self._watched_event_types.add(job.trigger.event_type)

    # 保留内部别名，方便内部调用
    _rebuild_event_index = rebuild_event_index

    # ---------- 定时器 ----------

    def _arm_timer(self) -> None:
        """取消旧定时器，创建新的延迟定时任务。"""
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
        """计算到最近到期 job 的延迟秒数，上限 60s。"""
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
        """定时器回调：扫描到期的 TimeTrigger jobs 并调用 on_trigger。"""
        try:
            now_ms = int(time.time() * 1000)
            for job in list(self._jobs.values()):
                if not job.enabled or job.id in self._running_jobs:
                    continue
                if not isinstance(job.trigger, TimeTrigger):
                    continue
                next_ms = job.state.next_trigger_at_ms
                if next_ms is not None and next_ms <= now_ms:
                    if len(self._running_jobs) >= self._max_concurrent:
                        break
                    await self._on_trigger(job)
        except Exception:
            logger.exception("ProactiveScheduler._on_timer error")
        finally:
            self._cleanup_debounce()
            self._arm_timer()

    # ---------- 事件循环 ----------

    async def _event_loop(self) -> None:
        """订阅 PublicEventBus，监听 EventTrigger 型 jobs。"""
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
                        await self._on_trigger(job)
                except Exception:
                    logger.exception("ProactiveScheduler event_loop handler error")
        except asyncio.CancelledError:
            pass

    # ---------- 清理 ----------

    def _cleanup_debounce(self) -> None:
        """移除 _last_event_fires 中超过 1 小时的过期条目。"""
        now_ms = int(time.time() * 1000)
        expired = [
            job_id
            for job_id, last_ms in self._last_event_fires.items()
            if (now_ms - last_ms) > _DEBOUNCE_EXPIRE_MS
        ]
        for job_id in expired:
            del self._last_event_fires[job_id]
        if expired:
            logger.debug("ProactiveScheduler: 清理过期 debounce 条目 %d 个", len(expired))
