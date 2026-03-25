"""ProactiveScheduler 单元测试。"""
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock

from sensenova_claw.kernel.proactive.models import (
    ProactiveJob, TimeTrigger, EventTrigger,
    ProactiveTask, DeliveryConfig, SafetyConfig, JobState,
)


def _make_job(trigger, **kwargs):
    defaults = dict(
        id="pj-sched-1",
        name="调度测试",
        agent_id="proactive-agent",
        trigger=trigger,
        task=ProactiveTask(prompt="测试"),
        delivery=DeliveryConfig(channels=["web"]),
        safety=SafetyConfig(max_duration_ms=5000),
        state=JobState(),
    )
    defaults.update(kwargs)
    return ProactiveJob(**defaults)


@pytest.mark.asyncio
async def test_cleanup_debounce_removes_expired():
    """验证 debounce 字典清理移除过期条目。"""
    from sensenova_claw.kernel.proactive.scheduler import ProactiveScheduler

    scheduler = ProactiveScheduler.__new__(ProactiveScheduler)
    scheduler._last_event_fires = {
        "old-job": int(time.time() * 1000) - 7_200_000,  # 2 小时前
        "recent-job": int(time.time() * 1000) - 60_000,  # 1 分钟前
    }

    scheduler._cleanup_debounce()

    assert "old-job" not in scheduler._last_event_fires
    assert "recent-job" in scheduler._last_event_fires


@pytest.mark.asyncio
async def test_compute_timer_delay_returns_max_when_no_jobs():
    """无 job 时返回最大延迟 60s。"""
    from sensenova_claw.kernel.proactive.scheduler import ProactiveScheduler, _MAX_TIMER_DELAY_S

    scheduler = ProactiveScheduler.__new__(ProactiveScheduler)
    scheduler._jobs = {}
    scheduler._running_jobs = set()

    delay = scheduler._compute_timer_delay()
    assert delay == _MAX_TIMER_DELAY_S


@pytest.mark.asyncio
async def test_compute_timer_delay_skips_disabled_jobs():
    """禁用的 job 不影响延迟计算。"""
    from sensenova_claw.kernel.proactive.scheduler import ProactiveScheduler, _MAX_TIMER_DELAY_S

    trigger = TimeTrigger(every="10s")
    job = _make_job(trigger, id="pj-disabled")
    job.enabled = False
    job.state.next_trigger_at_ms = int(time.time() * 1000) - 1000  # 已过期

    scheduler = ProactiveScheduler.__new__(ProactiveScheduler)
    scheduler._jobs = {job.id: job}
    scheduler._running_jobs = set()

    delay = scheduler._compute_timer_delay()
    assert delay == _MAX_TIMER_DELAY_S


@pytest.mark.asyncio
async def test_compute_timer_delay_uses_min_retrigger():
    """已过期的 job 延迟不低于 _MIN_RETRIGGER_S。"""
    from sensenova_claw.kernel.proactive.scheduler import ProactiveScheduler, _MIN_RETRIGGER_S

    trigger = TimeTrigger(every="10s")
    job = _make_job(trigger)
    job.state.next_trigger_at_ms = int(time.time() * 1000) - 5000  # 5 秒前已过期

    scheduler = ProactiveScheduler.__new__(ProactiveScheduler)
    scheduler._jobs = {job.id: job}
    scheduler._running_jobs = set()

    delay = scheduler._compute_timer_delay()
    assert delay == _MIN_RETRIGGER_S


@pytest.mark.asyncio
async def test_rebuild_event_index_only_includes_enabled_event_jobs():
    """rebuild_event_index 只收录启用的 EventTrigger jobs。"""
    from sensenova_claw.kernel.proactive.scheduler import ProactiveScheduler

    time_job = _make_job(TimeTrigger(every="1m"), id="pj-time")
    event_job_enabled = _make_job(
        EventTrigger(event_type="agent.step_completed", debounce_ms=1000),
        id="pj-event-on",
    )
    event_job_disabled = _make_job(
        EventTrigger(event_type="llm.call_completed", debounce_ms=1000),
        id="pj-event-off",
    )
    event_job_disabled.enabled = False

    scheduler = ProactiveScheduler.__new__(ProactiveScheduler)
    scheduler._jobs = {
        time_job.id: time_job,
        event_job_enabled.id: event_job_enabled,
        event_job_disabled.id: event_job_disabled,
    }
    scheduler._watched_event_types = set()

    scheduler.rebuild_event_index()

    assert "agent.step_completed" in scheduler._watched_event_types
    assert "llm.call_completed" not in scheduler._watched_event_types


@pytest.mark.asyncio
async def test_on_timer_calls_on_trigger_for_due_jobs():
    """_on_timer 对到期的 TimeTrigger job 调用 on_trigger。"""
    from sensenova_claw.kernel.proactive.scheduler import ProactiveScheduler

    trigger = TimeTrigger(every="10s")
    job = _make_job(trigger)
    job.state.next_trigger_at_ms = int(time.time() * 1000) - 1000  # 已过期

    on_trigger = AsyncMock(return_value=True)

    scheduler = ProactiveScheduler.__new__(ProactiveScheduler)
    scheduler._jobs = {job.id: job}
    scheduler._running_jobs = set()
    scheduler._max_concurrent = 3
    scheduler._on_trigger = on_trigger
    scheduler._last_event_fires = {}
    scheduler._timer_task = None

    # 替换 _arm_timer 避免创建真实 asyncio task
    scheduler._arm_timer = MagicMock()

    await scheduler._on_timer()

    on_trigger.assert_awaited_once_with(job)


@pytest.mark.asyncio
async def test_on_timer_skips_when_max_concurrent_reached():
    """达到最大并发数时，_on_timer 不再触发新 job。"""
    from sensenova_claw.kernel.proactive.scheduler import ProactiveScheduler

    trigger = TimeTrigger(every="10s")
    job1 = _make_job(trigger, id="pj-1")
    job2 = _make_job(trigger, id="pj-2")
    now_ms = int(time.time() * 1000) - 1000
    job1.state.next_trigger_at_ms = now_ms
    job2.state.next_trigger_at_ms = now_ms

    on_trigger = AsyncMock(return_value=True)

    scheduler = ProactiveScheduler.__new__(ProactiveScheduler)
    scheduler._jobs = {job1.id: job1, job2.id: job2}
    scheduler._running_jobs = {"pj-running-1"}  # 已有 1 个在跑
    scheduler._max_concurrent = 1  # 上限 1
    scheduler._on_trigger = on_trigger
    scheduler._last_event_fires = {}
    scheduler._timer_task = None
    scheduler._arm_timer = MagicMock()

    await scheduler._on_timer()

    on_trigger.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_debounce_keeps_recent_entries():
    """_cleanup_debounce 保留未过期的条目。"""
    from sensenova_claw.kernel.proactive.scheduler import ProactiveScheduler

    scheduler = ProactiveScheduler.__new__(ProactiveScheduler)
    now_ms = int(time.time() * 1000)
    scheduler._last_event_fires = {
        "job-a": now_ms - 100,        # 100ms 前，保留
        "job-b": now_ms - 3_599_999,  # 刚好未超过 1 小时，保留
    }

    scheduler._cleanup_debounce()

    assert "job-a" in scheduler._last_event_fires
    assert "job-b" in scheduler._last_event_fires
