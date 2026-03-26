"""Cron 调度计算

纯函数，无 I/O。用于计算 Job 的初始/下次触发时间和到期判定。
"""

from __future__ import annotations

from datetime import datetime, timezone, tzinfo as _tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sensenova_claw.kernel.scheduler.models import (
    AtSchedule,
    CronJob,
    CronSchedule,
    EverySchedule,
)


_WINDOWS_TZ_TO_IANA: dict[str, str] = {
    "China Standard Time": "Asia/Shanghai",
    "\u4e2d\u56fd\u6807\u51c6\u65f6\u95f4": "Asia/Shanghai",
    "Tokyo Standard Time": "Asia/Tokyo",
    "Korea Standard Time": "Asia/Seoul",
    "India Standard Time": "Asia/Kolkata",
    "Singapore Standard Time": "Asia/Singapore",
    "Taipei Standard Time": "Asia/Taipei",
    "Eastern Standard Time": "America/New_York",
    "Central Standard Time": "America/Chicago",
    "Mountain Standard Time": "America/Denver",
    "Pacific Standard Time": "America/Los_Angeles",
    "GMT Standard Time": "Europe/London",
    "W. Europe Standard Time": "Europe/Berlin",
    "Romance Standard Time": "Europe/Paris",
    "AUS Eastern Standard Time": "Australia/Sydney",
}

_OFFSET_SECONDS_TO_IANA: dict[int, str] = {
    28800: "Asia/Shanghai",
    32400: "Asia/Tokyo",
    19800: "Asia/Kolkata",
    -18000: "America/New_York",
    -21600: "America/Chicago",
    -25200: "America/Denver",
    -28800: "America/Los_Angeles",
    0: "Europe/London",
    3600: "Europe/Berlin",
    7200: "Europe/Helsinki",
    36000: "Australia/Sydney",
}


def _get_local_timezone() -> _tzinfo:
    """获取系统本地时区，用于 cron 调度默认值。
    优先返回 ZoneInfo（支持 DST），兜底返回固定偏移时区。
    """
    local = datetime.now(timezone.utc).astimezone().tzinfo
    key = getattr(local, "key", None)
    if key:
        try:
            return ZoneInfo(key)
        except (ZoneInfoNotFoundError, KeyError):
            pass

    import time as _time
    for name in _time.tzname:
        if not name:
            continue
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, KeyError):
            pass
        iana = _WINDOWS_TZ_TO_IANA.get(name)
        if iana:
            try:
                return ZoneInfo(iana)
            except (ZoneInfoNotFoundError, KeyError):
                pass

    offset = datetime.now(timezone.utc).astimezone().utcoffset()
    if offset:
        iana = _OFFSET_SECONDS_TO_IANA.get(int(offset.total_seconds()))
        if iana:
            try:
                return ZoneInfo(iana)
            except (ZoneInfoNotFoundError, KeyError):
                pass

    return local


def get_local_timezone_name() -> str | None:
    """获取系统本地 IANA 时区名（如 Asia/Shanghai），失败返回 None。"""
    tz = _get_local_timezone()
    key = getattr(tz, "key", None)
    return key if key else None


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
    """使用 croniter 计算下次触发时间（毫秒）。
    tz 为 None 时默认使用系统本地时区，而非 UTC。
    """
    from croniter import croniter

    if tz:
        try:
            base_tz: _tzinfo = ZoneInfo(tz)
        except ZoneInfoNotFoundError:
            base_tz = _get_local_timezone()
    else:
        base_tz = _get_local_timezone()
    base_dt = datetime.fromtimestamp(now_ms / 1000, tz=base_tz)
    cron = croniter(expr, base_dt)
    next_dt = cron.get_next(datetime)
    return int(next_dt.timestamp() * 1000)
