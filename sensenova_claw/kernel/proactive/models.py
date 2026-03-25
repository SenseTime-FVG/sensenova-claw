"""Proactive 数据模型

定义 ProactiveJob 及其子结构的数据类，以及 SQLite JSON 列的序列化/反序列化。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal


# ---------- 工具函数 ----------


def parse_duration_ms(s: str) -> int:
    """将时间字符串解析为毫秒数。支持 s/m/h/d 单位。"""
    match = re.fullmatch(r"(\d+)([smhd])", s.strip())
    if not match:
        raise ValueError(f"无法解析时间字符串: {s!r}，支持格式如 '5m', '1h', '30s', '2d'")
    value, unit = int(match.group(1)), match.group(2)
    multipliers = {"s": 1_000, "m": 60_000, "h": 3_600_000, "d": 86_400_000}
    return value * multipliers[unit]


# ---------- Trigger ----------


@dataclass
class TimeTrigger:
    """定时触发：支持 cron 表达式或 every 间隔"""
    kind: Literal["time"] = "time"
    cron: str | None = None
    every: str | None = None


@dataclass
class EventTrigger:
    """事件触发：监听指定事件类型"""
    kind: Literal["event"] = "event"
    event_type: str = ""
    filter: dict | None = None
    debounce_ms: int = 5000


Trigger = TimeTrigger | EventTrigger


# ---------- Task ----------


@dataclass
class ProactiveTask:
    """任务执行配置"""
    prompt: str = ""
    use_memory: bool = False
    system_prompt_override: str | None = None


# ---------- Delivery ----------


@dataclass
class DeliveryConfig:
    """投递配置"""
    channels: list[str] = field(default_factory=list)
    feishu_target: str | None = None
    summary_prompt: str | None = None


# ---------- Safety ----------


@dataclass
class SafetyConfig:
    """安全限制配置"""
    allowed_tools: list[str] | None = None
    blocked_tools: list[str] | None = None
    max_tool_calls: int = 20
    max_llm_calls: int = 10
    max_duration_ms: int = 300_000
    auto_disable_after_errors: int = 3


# ---------- JobState ----------


@dataclass
class JobState:
    """Job 运行时状态"""
    last_triggered_at_ms: int | None = None
    last_completed_at_ms: int | None = None
    last_status: str = "idle"
    consecutive_errors: int = 0
    total_runs: int = 0
    next_trigger_at_ms: int | None = None


# ---------- ProactiveJob ----------


@dataclass
class ProactiveJob:
    """主动任务定义"""
    id: str = ""
    name: str = ""
    agent_id: str = "proactive-agent"
    enabled: bool = True
    trigger: Trigger = field(default_factory=TimeTrigger)
    task: ProactiveTask = field(default_factory=ProactiveTask)
    delivery: DeliveryConfig = field(default_factory=DeliveryConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    state: JobState = field(default_factory=JobState)
    source: str = "config"


# ---------- 序列化 ----------


def trigger_to_json(trigger: Trigger) -> str:
    """Trigger → JSON 字符串"""
    if isinstance(trigger, TimeTrigger):
        return json.dumps({
            "kind": "time",
            "cron": trigger.cron,
            "every": trigger.every,
        })
    elif isinstance(trigger, EventTrigger):
        return json.dumps({
            "kind": "event",
            "event_type": trigger.event_type,
            "filter": trigger.filter,
            "debounce_ms": trigger.debounce_ms,
        })
    raise ValueError(f"未知 trigger 类型: {type(trigger)}")


def trigger_from_json(raw: str) -> Trigger:
    """JSON 字符串 → Trigger"""
    d = json.loads(raw)
    kind = d.get("kind")
    if kind == "time":
        return TimeTrigger(
            cron=d.get("cron"),
            every=d.get("every"),
        )
    elif kind == "event":
        return EventTrigger(
            event_type=d.get("event_type", ""),
            filter=d.get("filter"),
            debounce_ms=d.get("debounce_ms", 5000),
        )
    raise ValueError(f"Unknown trigger kind: {kind}")


def _task_to_dict(task: ProactiveTask) -> dict:
    return {
        "prompt": task.prompt,
        "use_memory": task.use_memory,
        "system_prompt_override": task.system_prompt_override,
    }


def _task_from_dict(d: dict) -> ProactiveTask:
    return ProactiveTask(
        prompt=d.get("prompt", ""),
        use_memory=d.get("use_memory", False),
        system_prompt_override=d.get("system_prompt_override"),
    )


def _delivery_to_dict(delivery: DeliveryConfig) -> dict:
    return {
        "channels": delivery.channels,
        "feishu_target": delivery.feishu_target,
        "summary_prompt": delivery.summary_prompt,
    }


def _delivery_from_dict(d: dict) -> DeliveryConfig:
    return DeliveryConfig(
        channels=d.get("channels", []),
        feishu_target=d.get("feishu_target"),
        summary_prompt=d.get("summary_prompt"),
    )


def _safety_to_dict(safety: SafetyConfig) -> dict:
    return {
        "allowed_tools": safety.allowed_tools,
        "blocked_tools": safety.blocked_tools,
        "max_tool_calls": safety.max_tool_calls,
        "max_llm_calls": safety.max_llm_calls,
        "max_duration_ms": safety.max_duration_ms,
        "auto_disable_after_errors": safety.auto_disable_after_errors,
    }


def _safety_from_dict(d: dict) -> SafetyConfig:
    return SafetyConfig(
        allowed_tools=d.get("allowed_tools"),
        blocked_tools=d.get("blocked_tools"),
        max_tool_calls=d.get("max_tool_calls", 20),
        max_llm_calls=d.get("max_llm_calls", 10),
        max_duration_ms=d.get("max_duration_ms", 300_000),
        auto_disable_after_errors=d.get("auto_disable_after_errors", 3),
    )


def _state_to_dict(state: JobState) -> dict:
    return {
        "last_triggered_at_ms": state.last_triggered_at_ms,
        "last_completed_at_ms": state.last_completed_at_ms,
        "last_status": state.last_status,
        "consecutive_errors": state.consecutive_errors,
        "total_runs": state.total_runs,
        "next_trigger_at_ms": state.next_trigger_at_ms,
    }


def _state_from_dict(d: dict) -> JobState:
    return JobState(
        last_triggered_at_ms=d.get("last_triggered_at_ms"),
        last_completed_at_ms=d.get("last_completed_at_ms"),
        last_status=d.get("last_status", "idle"),
        consecutive_errors=d.get("consecutive_errors", 0),
        total_runs=d.get("total_runs", 0),
        next_trigger_at_ms=d.get("next_trigger_at_ms"),
    )


def job_to_db_row(job: ProactiveJob) -> dict[str, Any]:
    """ProactiveJob → 扁平 dict，用于 DB 插入"""
    return {
        "id": job.id,
        "name": job.name,
        "agent_id": job.agent_id,
        "enabled": 1 if job.enabled else 0,
        "trigger_json": trigger_to_json(job.trigger),
        "task_json": json.dumps(_task_to_dict(job.task)),
        "delivery_json": json.dumps(_delivery_to_dict(job.delivery)),
        "safety_json": json.dumps(_safety_to_dict(job.safety)),
        "state_json": json.dumps(_state_to_dict(job.state)),
        "source": job.source,
    }


def job_from_db_row(row: dict[str, Any]) -> ProactiveJob:
    """DB 行 dict → ProactiveJob"""
    return ProactiveJob(
        id=row["id"],
        name=row.get("name", ""),
        agent_id=row.get("agent_id", "proactive-agent"),
        enabled=bool(row.get("enabled", 1)),
        trigger=trigger_from_json(row["trigger_json"]),
        task=_task_from_dict(json.loads(row.get("task_json", "{}"))),
        delivery=_delivery_from_dict(json.loads(row.get("delivery_json", "{}"))),
        safety=_safety_from_dict(json.loads(row.get("safety_json", "{}"))),
        state=_state_from_dict(json.loads(row.get("state_json", "{}"))),
        source=row.get("source", "config"),
    )
