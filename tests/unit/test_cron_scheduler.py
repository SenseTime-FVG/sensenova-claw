"""Cron 调度计算单元测试"""

import time
import pytest

from sensenova_claw.kernel.scheduler.models import (
    AtSchedule,
    CronJob,
    CronJobState,
    CronSchedule,
    EverySchedule,
    SystemEventPayload,
)
from sensenova_claw.kernel.scheduler.scheduler import (
    compute_initial_next_run_ms,
    compute_next_run_at_ms,
    is_job_runnable,
)


class TestComputeInitialNextRunMs:
    def test_at_schedule(self):
        job = CronJob(schedule=AtSchedule(at="2026-03-15T10:00:00+00:00"))
        now_ms = int(time.time() * 1000)
        result = compute_initial_next_run_ms(job, now_ms)
        assert result is not None
        # 2026-03-15T10:00:00+00:00 的毫秒时间戳
        from datetime import datetime, timezone
        expected = int(datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
        assert result == expected

    def test_every_schedule_no_anchor(self):
        now_ms = 1000000
        job = CronJob(schedule=EverySchedule(every_ms=60000))
        result = compute_initial_next_run_ms(job, now_ms)
        assert result == now_ms + 60000

    def test_every_schedule_with_anchor(self):
        anchor_ms = 1000000
        now_ms = 1150000  # anchor + 150000
        job = CronJob(schedule=EverySchedule(every_ms=60000, anchor_ms=anchor_ms))
        result = compute_initial_next_run_ms(job, now_ms)
        # periods = max(0, (1150000 - 1000000) // 60000) = 2
        # next = max(1000000 + 3 * 60000, 1150001) = max(1180000, 1150001) = 1180000
        assert result == 1180000

    def test_cron_schedule(self):
        now_ms = int(time.time() * 1000)
        job = CronJob(schedule=CronSchedule(expr="*/5 * * * *"))
        result = compute_initial_next_run_ms(job, now_ms)
        assert result is not None
        # 下次触发应在未来
        assert result > now_ms
        # 不超过 5 分钟 + 一点误差
        assert result <= now_ms + 5 * 60 * 1000 + 1000


class TestComputeNextRunAtMs:
    def test_at_schedule_returns_none(self):
        job = CronJob(schedule=AtSchedule(at="2026-03-15T10:00:00+00:00"))
        result = compute_next_run_at_ms(job, 1000000)
        assert result is None

    def test_every_schedule_no_anchor(self):
        now_ms = 2000000
        job = CronJob(schedule=EverySchedule(every_ms=30000))
        result = compute_next_run_at_ms(job, now_ms)
        assert result == now_ms + 30000

    def test_every_schedule_with_anchor(self):
        anchor_ms = 1000000
        now_ms = 1150000
        job = CronJob(schedule=EverySchedule(every_ms=60000, anchor_ms=anchor_ms))
        result = compute_next_run_at_ms(job, now_ms)
        # periods = (1150000 - 1000000) // 60000 = 2
        # next = max(1000000 + 3 * 60000, 1150001) = 1180000
        assert result == 1180000

    def test_cron_schedule(self):
        now_ms = int(time.time() * 1000)
        job = CronJob(schedule=CronSchedule(expr="0 * * * *"))
        result = compute_next_run_at_ms(job, now_ms)
        assert result is not None
        assert result > now_ms


class TestIsJobRunnable:
    def test_disabled_job(self):
        job = CronJob(enabled=False, state=CronJobState(next_run_at_ms=0))
        assert is_job_runnable(job, 1000) is False

    def test_running_job(self):
        job = CronJob(state=CronJobState(next_run_at_ms=0, running_at_ms=500))
        assert is_job_runnable(job, 1000) is False

    def test_not_yet_due(self):
        job = CronJob(state=CronJobState(next_run_at_ms=2000))
        assert is_job_runnable(job, 1000) is False

    def test_due_job(self):
        job = CronJob(state=CronJobState(next_run_at_ms=500))
        assert is_job_runnable(job, 1000) is True

    def test_forced(self):
        job = CronJob(state=CronJobState(next_run_at_ms=99999))
        assert is_job_runnable(job, 1000, forced=True) is True

    def test_no_next_run_at_ms(self):
        job = CronJob(state=CronJobState(next_run_at_ms=None))
        assert is_job_runnable(job, 1000) is False
