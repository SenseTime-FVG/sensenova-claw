"""Cron Agent Tool — 让 Agent 管理定时任务

支持操作: add（添加）、list（列出）、remove（删除）。
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from app.cron.models import (
    AtSchedule,
    CronJob,
    CronSchedule,
    EverySchedule,
    SystemEventPayload,
)
from app.tools.base import Tool, ToolRiskLevel

if TYPE_CHECKING:
    from app.cron.runtime import CronRuntime


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

        # 构建 Schedule
        if schedule_type == "at":
            schedule = AtSchedule(at=schedule_value)
        elif schedule_type == "every":
            schedule = EverySchedule(every_ms=int(schedule_value))
        elif schedule_type == "cron":
            schedule = CronSchedule(expr=schedule_value)
        else:
            return {"error": f"未知调度类型: {schedule_type}"}

        # 根据当前 session 自动解析投递目标
        delivery = self._runtime.resolve_delivery_for_session(session_id)

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
