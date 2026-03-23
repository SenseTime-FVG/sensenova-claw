"""触发器评估逻辑。"""
from __future__ import annotations
import time
from agentos.kernel.proactive.models import (
    ProactiveJob, TimeTrigger, EventTrigger, ConditionTrigger,
    parse_duration_ms,
)
from agentos.kernel.scheduler.scheduler import _croniter_next_ms


def compute_next_fire_ms(job: ProactiveJob, now_ms: int) -> int | None:
    """计算 job 的下次触发时间（毫秒）。EventTrigger 返回 None。"""
    trigger = job.trigger
    if isinstance(trigger, TimeTrigger):
        if trigger.cron:
            return _croniter_next_ms(trigger.cron, now_ms, None)
        elif trigger.every:
            return now_ms + parse_duration_ms(trigger.every)
    elif isinstance(trigger, ConditionTrigger):
        return now_ms + parse_duration_ms(trigger.check_interval)
    return None


def is_event_match(trigger: EventTrigger, event_type: str, payload: dict) -> bool:
    """检查事件是否匹配 EventTrigger。"""
    if trigger.event_type != event_type:
        return False
    if trigger.filter:
        for k, v in trigger.filter.items():
            if payload.get(k) != v:
                return False
    return True


def should_debounce(job_id: str, debounce_ms: int, last_fires: dict[str, int]) -> bool:
    """Leading-edge 防抖：如果在 debounce 窗口内已触发过，返回 True。"""
    now_ms = int(time.time() * 1000)
    last = last_fires.get(job_id)
    if last is None:
        return False
    return (now_ms - last) < debounce_ms


def build_condition_prompt(condition: str, context: str | None = None) -> str:
    """构建条件评估 prompt。"""
    parts = [
        "你是一个条件评估器。根据以下信息判断条件是否满足。",
        f"条件: {condition}",
        f"当前时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    if context:
        parts.append(f"上下文: {context}")
    parts.append("请只回答 YES 或 NO，不要解释。")
    return "\n".join(parts)


def parse_condition_response(response: str) -> bool:
    """解析 LLM 条件评估响应。非 YES 一律视为 False。"""
    return response.strip().upper() == "YES"
