"""触发器评估逻辑。"""
from __future__ import annotations
import time
from sensenova_claw.kernel.proactive.models import (
    ProactiveJob, TimeTrigger, EventTrigger,
    parse_duration_ms,
)
from sensenova_claw.kernel.scheduler.scheduler import _croniter_next_ms


def compute_next_fire_ms(job: ProactiveJob, now_ms: int) -> int | None:
    """计算 job 的下次触发时间（毫秒）。EventTrigger 返回 None。"""
    trigger = job.trigger
    if isinstance(trigger, TimeTrigger):
        if trigger.cron:
            return _croniter_next_ms(trigger.cron, now_ms, None)
        elif trigger.every:
            return now_ms + parse_duration_ms(trigger.every)
    return None


def is_event_match(trigger: EventTrigger, event_type: str, payload: dict) -> bool:
    """检查事件是否匹配 EventTrigger。"""
    if trigger.event_type != event_type:
        return False
    if trigger.filter:
        for k, v in trigger.filter.items():
            if payload.get(k) != v:
                return False
    if trigger.exclude_payload:
        for k, v in trigger.exclude_payload.items():
            if payload.get(k) == v:
                return False
    return True


def should_debounce(job_id: str, debounce_ms: int, last_fires: dict[str, int]) -> bool:
    """Leading-edge 防抖：如果在 debounce 窗口内已触发过，返回 True。"""
    now_ms = int(time.time() * 1000)
    last = last_fires.get(job_id)
    if last is None:
        return False
    return (now_ms - last) < debounce_ms
