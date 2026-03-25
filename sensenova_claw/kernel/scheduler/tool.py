"""Cron Agent Tool — 让 Agent 管理定时任务

支持操作: add（添加）、list（列出）、remove（删除）。
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from sensenova_claw.kernel.scheduler.models import (
    AtSchedule,
    CronDelivery,
    CronJob,
    CronSchedule,
    EverySchedule,
    SystemEventPayload,
)
from sensenova_claw.capabilities.tools.base import Tool, ToolRiskLevel
from sensenova_claw.platform.config.config import config

if TYPE_CHECKING:
    from sensenova_claw.kernel.scheduler.runtime import CronRuntime


def _resolve_cron_timezone() -> str | None:
    """从配置或系统时区解析 cron 使用的时区。
    配置值 "local" 表示读取系统本地时区，其他值直接作为 IANA 时区名。
    """
    tz_cfg = config.get("cron.timezone", "local")
    if not tz_cfg or tz_cfg == "local":
        import time as _time
        import datetime as _dt
        # 通过 datetime 获取系统本地时区的 IANA 名称
        local_tz = _dt.datetime.now(_dt.timezone.utc).astimezone().tzinfo
        tz_name = getattr(local_tz, "key", None)  # Python 3.9+ ZoneInfo
        if tz_name:
            return tz_name
        # 回退：用 time.tzname 尝试获取
        name = _time.tzname[0]
        return name if name else None
    return tz_cfg


class CronTool(Tool):
    name = "cron_manage"
    description = (
        "管理定时任务。支持操作: add（添加定时任务）, list（列出所有任务）, remove（删除任务）。"
        "添加时需要指定 schedule_type（at/every/cron）和对应参数。"
    )
    risk_level = ToolRiskLevel.MEDIUM
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "list", "remove"],
                "description": "操作类型",
            },
            "name": {
                "type": "string",
                "description": "任务名称（add 时可选）",
            },
            "schedule_type": {
                "type": "string",
                "enum": ["at", "every", "cron"],
                "description": "调度类型（add 时必填）: at=一次性, every=周期, cron=cron表达式",
            },
            "schedule_value": {
                "type": "string",
                "description": "调度参数: at='ISO 8601时间', every='毫秒数', cron='cron表达式'",
            },
            "text": {
                "type": "string",
                "description": "系统事件文本（add 时必填，将注入 heartbeat prompt）",
            },
            "job_id": {
                "type": "string",
                "description": "任务ID（remove 时必填）",
            },
            "send_to_current_session": {
                "type": "boolean",
                "description": "是否将提醒消息发送回当前会话，默认 true",
            },
            "notification_channels": {
                "type": "array",
                "items": {"type": "string", "enum": ["browser", "native"]},
                "description": "额外通知渠道，如 browser/native",
            },
        },
        "required": ["action"],
    }

    def __init__(self, cron_runtime: CronRuntime):
        self._runtime = cron_runtime

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "")
        if action == "add":
            return await self._add(kwargs)
        elif action == "list":
            return await self._list()
        elif action == "remove":
            return await self._remove(kwargs)
        return {"error": f"未知操作: {action}"}

    async def _add(self, kwargs: dict) -> dict:
        schedule_type = kwargs.get("schedule_type", "every")
        schedule_value = kwargs.get("schedule_value", "")
        text = kwargs.get("text", "")
        name = kwargs.get("name")
        session_id = kwargs.get("_session_id", "")
        send_to_current_session = bool(kwargs.get("send_to_current_session", True))
        notification_channels = [
            channel
            for channel in kwargs.get("notification_channels", [])
            if channel in {"browser", "native"}
        ]

        # 构建 Schedule
        if schedule_type == "at":
            schedule = AtSchedule(at=schedule_value)
        elif schedule_type == "every":
            schedule = EverySchedule(every_ms=int(schedule_value))
        elif schedule_type == "cron":
            tz = _resolve_cron_timezone()
            schedule = CronSchedule(expr=schedule_value, tz=tz)
        else:
            return {"error": f"未知调度类型: {schedule_type}"}

        delivery = None
        if send_to_current_session and session_id:
            delivery = self._runtime.resolve_delivery_for_session(session_id)
        elif notification_channels:
            delivery = CronDelivery(mode="none", session_id=session_id or None)

        if delivery:
            delivery.notification_channels = notification_channels

        job = CronJob(
            name=name,
            schedule=schedule,
            session_target="main",
            payload=SystemEventPayload(text=text),
            delivery=delivery,
        )
        job = await self._runtime.add_job(job)
        return {
            "success": True,
            "job_id": job.id,
            "name": job.name,
            "next_run_at_ms": job.state.next_run_at_ms,
            "delivery_channel": delivery.channel_id if delivery else None,
            "delivery_session_id": delivery.session_id if delivery else None,
            "notification_channels": delivery.notification_channels if delivery else [],
        }

    async def _list(self) -> dict:
        jobs = await self._runtime.list_jobs()
        return {
            "jobs": [
                {
                    "id": j.id,
                    "name": j.name,
                    "enabled": j.enabled,
                    "schedule_kind": j.schedule.kind,
                    "next_run_at_ms": j.state.next_run_at_ms,
                    "last_run_status": j.state.last_run_status,
                }
                for j in jobs
            ]
        }

    async def _remove(self, kwargs: dict) -> dict:
        job_id = kwargs.get("job_id", "")
        if not job_id:
            return {"error": "job_id 必填"}
        removed = await self._runtime.remove_job(job_id)
        return {"success": removed, "job_id": job_id}
