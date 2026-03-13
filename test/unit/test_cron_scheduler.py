"""R02: CronScheduler 时间计算"""
import time
from agentos.kernel.scheduler.models import (
    CronJob, CronJobState,
    AtSchedule, EverySchedule, CronSchedule,
    SystemEventPayload,
)
from agentos.kernel.scheduler.scheduler import compute_initial_next_run_ms, compute_next_run_at_ms, is_job_runnable


def _make_job(schedule, **kwargs) -> CronJob:
    return CronJob(
        id="test_job",
        schedule=schedule,
        payload=SystemEventPayload(text="hi"),
        created_at_ms=int(time.time() * 1000),
        updated_at_ms=int(time.time() * 1000),
        state=CronJobState(**kwargs),
    )


class TestCronScheduler:
    def test_at_initial_next_run(self):
        s = AtSchedule(at="2026-12-31T23:59:59")
        job = _make_job(s)
        now = int(time.time() * 1000)
        result = compute_initial_next_run_ms(job, now)
        assert result is not None
        assert result > now  # 未来的时间

    def test_every_initial_next_run(self):
        s = EverySchedule(every_ms=60000)
        job = _make_job(s)
        now = int(time.time() * 1000)
        result = compute_initial_next_run_ms(job, now)
        assert result is not None
        assert result >= now

    def test_every_next_run_after_execution(self):
        s = EverySchedule(every_ms=60000)
        job = _make_job(s)
        now = int(time.time() * 1000)
        result = compute_next_run_at_ms(job, now)
        assert result is not None
        assert result >= now

    def test_at_next_run_returns_none(self):
        """at 类型执行后应返回 None（一次性）"""
        s = AtSchedule(at="2026-03-12T10:00:00")
        job = _make_job(s)
        now = int(time.time() * 1000)
        result = compute_next_run_at_ms(job, now)
        assert result is None

    def test_is_runnable_true(self):
        s = EverySchedule(every_ms=60000)
        now = int(time.time() * 1000)
        job = _make_job(s, next_run_at_ms=now - 1000)
        assert is_job_runnable(job, now) is True

    def test_is_runnable_not_yet(self):
        s = EverySchedule(every_ms=60000)
        now = int(time.time() * 1000)
        job = _make_job(s, next_run_at_ms=now + 60000)
        assert is_job_runnable(job, now) is False

    def test_is_runnable_disabled(self):
        s = EverySchedule(every_ms=60000)
        now = int(time.time() * 1000)
        job = _make_job(s, next_run_at_ms=now - 1000)
        job.enabled = False
        assert is_job_runnable(job, now) is False

    def test_is_runnable_already_running(self):
        s = EverySchedule(every_ms=60000)
        now = int(time.time() * 1000)
        job = _make_job(s, next_run_at_ms=now - 1000, running_at_ms=now - 500)
        assert is_job_runnable(job, now) is False
