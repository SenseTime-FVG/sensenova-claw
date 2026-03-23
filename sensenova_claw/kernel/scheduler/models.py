"""Cron 数据模型

定义 CronJob 及其子结构的数据类，以及 SQLite JSON 列的序列化/反序列化。
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal


# ---------- Schedule ----------


@dataclass
class AtSchedule:
    """一次性定时任务：到指定时间触发"""
    kind: Literal["at"] = "at"
    at: str = ""  # ISO 8601 datetime


@dataclass
class EverySchedule:
    """周期性任务：每隔 every_ms 毫秒触发"""
    kind: Literal["every"] = "every"
    every_ms: int = 0
    anchor_ms: int | None = None


@dataclass
class CronSchedule:
    """Cron 表达式调度"""
    kind: Literal["cron"] = "cron"
    expr: str = ""
    tz: str | None = None
    stagger_ms: int | None = None  # Phase 2


Schedule = AtSchedule | EverySchedule | CronSchedule


# ---------- Payload ----------


@dataclass
class SystemEventPayload:
    """主会话系统事件：注入 Heartbeat prompt"""
    kind: Literal["systemEvent"] = "systemEvent"
    text: str = ""


@dataclass
class AgentTurnPayload:
    """隔离会话 Agent Turn"""
    kind: Literal["agentTurn"] = "agentTurn"
    agent_id: str = "default"
    message: str = ""
    model: str | None = None
    timeout_seconds: int | None = None
    light_context: bool = False


Payload = SystemEventPayload | AgentTurnPayload


# ---------- Delivery ----------


@dataclass
class CronDelivery:
    """投递配置"""
    mode: Literal["none", "announce"] = "announce"
    channel_id: str | None = None
    to: str | None = None
    session_id: str | None = None
    notification_channels: list[str] | None = None
    best_effort: bool = False


# ---------- CronJobState ----------


@dataclass
class CronJobState:
    """Job 运行时状态（内嵌在 cron_jobs 行中）"""
    next_run_at_ms: int | None = None
    running_at_ms: int | None = None
    last_run_at_ms: int | None = None
    last_run_status: Literal["ok", "error", "skipped"] | None = None
    last_error: str | None = None
    last_duration_ms: int | None = None
    consecutive_errors: int = 0


# ---------- CronJob ----------


@dataclass
class CronJob:
    id: str = field(default_factory=lambda: f"cron_{uuid.uuid4().hex[:12]}")
    name: str | None = None
    description: str | None = None
    schedule: Schedule = field(default_factory=AtSchedule)
    session_target: Literal["main", "isolated"] = "isolated"
    wake_mode: Literal["now", "next-heartbeat"] = "now"
    payload: Payload = field(default_factory=AgentTurnPayload)
    delivery: CronDelivery | None = None
    enabled: bool = True
    delete_after_run: bool | None = None
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    updated_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    state: CronJobState = field(default_factory=CronJobState)


# ---------- 序列化 ----------


def schedule_to_json(schedule: Schedule) -> str:
    """Schedule → JSON 字符串"""
    if isinstance(schedule, AtSchedule):
        return json.dumps({"kind": "at", "at": schedule.at})
    elif isinstance(schedule, EverySchedule):
        return json.dumps({"kind": "every", "every_ms": schedule.every_ms, "anchor_ms": schedule.anchor_ms})
    elif isinstance(schedule, CronSchedule):
        return json.dumps({"kind": "cron", "expr": schedule.expr, "tz": schedule.tz, "stagger_ms": schedule.stagger_ms})
    raise ValueError(f"Unknown schedule type: {type(schedule)}")


def schedule_from_json(raw: str) -> Schedule:
    """JSON 字符串 → Schedule"""
    d = json.loads(raw)
    kind = d.get("kind")
    if kind == "at":
        return AtSchedule(at=d.get("at", ""))
    elif kind == "every":
        return EverySchedule(every_ms=d.get("every_ms", 0), anchor_ms=d.get("anchor_ms"))
    elif kind == "cron":
        return CronSchedule(expr=d.get("expr", ""), tz=d.get("tz"), stagger_ms=d.get("stagger_ms"))
    raise ValueError(f"Unknown schedule kind: {kind}")


def payload_to_json(payload: Payload) -> str:
    """Payload → JSON 字符串"""
    if isinstance(payload, SystemEventPayload):
        return json.dumps({"kind": "systemEvent", "text": payload.text})
    elif isinstance(payload, AgentTurnPayload):
        return json.dumps({
            "kind": "agentTurn",
            "agent_id": payload.agent_id,
            "message": payload.message,
            "model": payload.model,
            "timeout_seconds": payload.timeout_seconds,
            "light_context": payload.light_context,
        })
    raise ValueError(f"Unknown payload type: {type(payload)}")


def payload_from_json(raw: str) -> Payload:
    """JSON 字符串 → Payload"""
    d = json.loads(raw)
    kind = d.get("kind")
    if kind == "systemEvent":
        return SystemEventPayload(text=d.get("text", ""))
    elif kind == "agentTurn":
        return AgentTurnPayload(
            agent_id=d.get("agent_id", "default"),
            message=d.get("message", ""),
            model=d.get("model"),
            timeout_seconds=d.get("timeout_seconds"),
            light_context=d.get("light_context", False),
        )
    raise ValueError(f"Unknown payload kind: {kind}")


def delivery_to_json(delivery: CronDelivery | None) -> str | None:
    """Delivery → JSON 字符串"""
    if delivery is None:
        return None
    return json.dumps({
        "mode": delivery.mode,
        "channel_id": delivery.channel_id,
        "to": delivery.to,
        "session_id": delivery.session_id,
        "notification_channels": delivery.notification_channels,
        "best_effort": delivery.best_effort,
    })


def delivery_from_json(raw: str | None) -> CronDelivery | None:
    """JSON 字符串 → Delivery"""
    if raw is None:
        return None
    d = json.loads(raw)
    return CronDelivery(
        mode=d.get("mode", "announce"),
        channel_id=d.get("channel_id"),
        to=d.get("to"),
        session_id=d.get("session_id"),
        notification_channels=d.get("notification_channels"),
        best_effort=d.get("best_effort", False),
    )


def cron_job_to_db_row(job: CronJob) -> dict[str, Any]:
    """CronJob → 扁平 dict，用于 DB 插入"""
    return {
        "id": job.id,
        "name": job.name,
        "description": job.description,
        "schedule_json": schedule_to_json(job.schedule),
        "session_target": job.session_target,
        "wake_mode": job.wake_mode,
        "payload_json": payload_to_json(job.payload),
        "delivery_json": delivery_to_json(job.delivery),
        "enabled": 1 if job.enabled else 0,
        "delete_after_run": 1 if job.delete_after_run else (0 if job.delete_after_run is False else None),
        "created_at_ms": job.created_at_ms,
        "updated_at_ms": job.updated_at_ms,
        "next_run_at_ms": job.state.next_run_at_ms,
        "running_at_ms": job.state.running_at_ms,
        "last_run_at_ms": job.state.last_run_at_ms,
        "last_run_status": job.state.last_run_status,
        "last_error": job.state.last_error,
        "last_duration_ms": job.state.last_duration_ms,
        "consecutive_errors": job.state.consecutive_errors,
    }


def cron_job_from_db_row(row: dict[str, Any]) -> CronJob:
    """DB 行 dict → CronJob"""
    return CronJob(
        id=row["id"],
        name=row.get("name"),
        description=row.get("description"),
        schedule=schedule_from_json(row["schedule_json"]),
        session_target=row.get("session_target", "isolated"),
        wake_mode=row.get("wake_mode", "now"),
        payload=payload_from_json(row["payload_json"]),
        delivery=delivery_from_json(row.get("delivery_json")),
        enabled=bool(row.get("enabled", 1)),
        delete_after_run=None if row.get("delete_after_run") is None else bool(row["delete_after_run"]),
        created_at_ms=row.get("created_at_ms", 0),
        updated_at_ms=row.get("updated_at_ms", 0),
        state=CronJobState(
            next_run_at_ms=row.get("next_run_at_ms"),
            running_at_ms=row.get("running_at_ms"),
            last_run_at_ms=row.get("last_run_at_ms"),
            last_run_status=row.get("last_run_status"),
            last_error=row.get("last_error"),
            last_duration_ms=row.get("last_duration_ms"),
            consecutive_errors=row.get("consecutive_errors", 0),
        ),
    )
