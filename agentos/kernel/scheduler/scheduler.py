"""Cron 调度计算

纯函数，无 I/O。用于计算 Job 的初始/下次触发时间和到期判定。
"""

from __future__ import annotations

from datetime import datetime, timezone

from agentos.kernel.scheduler.models import (
    AtSchedule,
    CronJob,
    CronSchedule,
    EverySchedule,
)


def compute_initial_next_run_ms(job: CronJob, now_ms: int) -> int | None:
    """新建 Job 时计算首次 next_run_at_ms"""
    match job.schedule:
        case AtSchedule(at=at_str):
            dt = datetime.fromisoformat(at_str)
            return int(dt.timestamp() * 1000)
        case EverySchedule(every_ms=interval, anchor_ms=anchor):
            if anchor is not None:
                periods = max(0, (now_ms - anchor) // interval)
                return max(anchor + (periods + 1) * interval, now_ms + 1)
            return now_ms + interval
        case CronSchedule(expr=expr, tz=tz):
            return _croniter_next_ms(expr, now_ms, tz)
    return None


def compute_next_run_at_ms(job: CronJob, now_ms: int) -> int | None:
    """执行完成后计算下一次触发时间"""
    match job.schedule:
        case AtSchedule():
            return None  # 一次性任务，无下次
        case EverySchedule(every_ms=interval, anchor_ms=anchor):
            if anchor is None:
                return now_ms + interval
            periods = (now_ms - anchor) // interval
            return max(anchor + (periods + 1) * interval, now_ms + 1)
        case CronSchedule(expr=expr, tz=tz):
            return _croniter_next_ms(expr, now_ms, tz)
    return None


def is_job_runnable(job: CronJob, now_ms: int, *, forced: bool = False) -> bool:
    """判断 Job 是否应当执行"""
    if not job.enabled or job.state.running_at_ms is not None:
        return False
    if forced:
        return True
    return (
        isinstance(job.state.next_run_at_ms, int)
        and now_ms >= job.state.next_run_at_ms
    )


def _croniter_next_ms(expr: str, now_ms: int, tz: str | None) -> int:
    """使用 croniter 计算下次触发时间（毫秒）"""
    from croniter import croniter

    base_dt = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc)
    cron = croniter(expr, base_dt)
    next_dt = cron.get_next(datetime)
    return int(next_dt.timestamp() * 1000)
