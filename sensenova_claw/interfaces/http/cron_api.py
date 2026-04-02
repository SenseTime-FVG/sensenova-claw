"""Cron REST API。"""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from sensenova_claw.kernel.scheduler.models import (
    AtSchedule,
    CronDelivery,
    CronJob,
    CronSchedule,
    EverySchedule,
    SystemEventPayload,
)

router = APIRouter(prefix="/api/cron", tags=["cron"])
_UNSET = object()


class CronJobCreateBody(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    schedule_type: Literal["at", "every", "cron"]
    schedule_value: str
    timezone: str | None = None
    text: str = ""
    session_target: Literal["main", "isolated"] = "main"
    wake_mode: Literal["now", "next-heartbeat"] = "now"
    delete_after_run: bool | None = None
    enabled: bool = True
    delivery_session_id: str | None = None
    notification_channels: list[Literal["browser", "native"]] = Field(default_factory=list)


class CronJobUpdateBody(BaseModel):
    name: str | None = None
    description: str | None = None
    schedule_type: Literal["at", "every", "cron"] | None = None
    schedule_value: str | None = None
    timezone: str | None = None
    text: str | None = None
    session_target: Literal["main", "isolated"] | None = None
    wake_mode: Literal["now", "next-heartbeat"] | None = None
    delete_after_run: bool | None = None
    enabled: bool | None = None
    delivery_session_id: str | None = None
    notification_channels: list[Literal["browser", "native"]] | None = None


def _runtime(request: Request):
    return request.app.state.services.cron_runtime


def _build_schedule(schedule_type: str, schedule_value: str, timezone: str | None):
    if schedule_type == "at":
        return AtSchedule(at=schedule_value)
    if schedule_type == "every":
        return EverySchedule(every_ms=int(schedule_value))
    if schedule_type == "cron":
        from sensenova_claw.kernel.scheduler.scheduler import get_local_timezone_name
        tz = timezone or get_local_timezone_name()
        return CronSchedule(expr=schedule_value, tz=tz)
    raise HTTPException(400, f"Unsupported schedule_type: {schedule_type}")


def _build_delivery(
    runtime,
    *,
    delivery_session_id: str | None | object,
    notification_channels: list[str] | None,
    existing: CronDelivery | None = None,
) -> CronDelivery | None:
    base_delivery = existing
    effective_session_id = existing.session_id if existing else None
    effective_channels = (
        list(notification_channels)
        if notification_channels is not None
        else list(existing.notification_channels or []) if existing else []
    )

    if delivery_session_id is not _UNSET:
        if delivery_session_id in ("", None):
            base_delivery = None
            effective_session_id = None
        else:
            base_delivery = runtime.resolve_delivery_for_session(delivery_session_id)
            if not base_delivery:
                raise HTTPException(400, f"Unknown or unbound session_id: {delivery_session_id}")
            effective_session_id = delivery_session_id

    if not base_delivery and (effective_session_id or effective_channels):
        base_delivery = CronDelivery(mode="none", session_id=effective_session_id)

    if not base_delivery:
        return None

    base_delivery.session_id = effective_session_id
    base_delivery.notification_channels = effective_channels

    if base_delivery.mode == "none" and not base_delivery.session_id and not effective_channels:
        return None

    return base_delivery


def _serialize_job(job: CronJob) -> dict:
    schedule_value = ""
    timezone = None
    if isinstance(job.schedule, AtSchedule):
        schedule_value = job.schedule.at
    elif isinstance(job.schedule, EverySchedule):
        schedule_value = str(job.schedule.every_ms)
    elif isinstance(job.schedule, CronSchedule):
        schedule_value = job.schedule.expr
        timezone = job.schedule.tz

    text = job.payload.text if isinstance(job.payload, SystemEventPayload) else ""

    return {
        "id": job.id,
        "name": job.name,
        "description": job.description,
        "schedule_type": job.schedule.kind,
        "schedule_value": schedule_value,
        "timezone": timezone,
        "text": text,
        "session_target": job.session_target,
        "wake_mode": job.wake_mode,
        "enabled": job.enabled,
        "delete_after_run": job.delete_after_run,
        "delivery": None if not job.delivery else {
            "mode": job.delivery.mode,
            "channel_id": job.delivery.channel_id,
            "to": job.delivery.to,
            "session_id": job.delivery.session_id,
            "notification_channels": job.delivery.notification_channels or [],
            "best_effort": job.delivery.best_effort,
        },
        "next_run_at_ms": job.state.next_run_at_ms,
        "running_at_ms": job.state.running_at_ms,
        "last_run_at_ms": job.state.last_run_at_ms,
        "last_run_status": job.state.last_run_status,
        "last_error": job.state.last_error,
        "last_duration_ms": job.state.last_duration_ms,
        "consecutive_errors": job.state.consecutive_errors,
        "created_at_ms": job.created_at_ms,
        "updated_at_ms": job.updated_at_ms,
    }


def _ensure_supported_target(session_target: str | None) -> None:
    if session_target == "isolated":
        raise HTTPException(400, "session_target='isolated' is not supported yet")


@router.get("/runs")
async def list_all_cron_runs(request: Request, limit: int = 50, status: str | None = None):
    """跨所有 job 返回 cron runs，附带 job 名称和提醒文本。"""
    rows = await _runtime(request)._repo.list_all_cron_runs(limit=limit, status=status)
    runs = []
    for row in rows:
        # 优先从 run 自身冗余字段读取（job 可能已被自动删除）
        name = row.get("job_name") or row.get("joined_job_name") or row["job_id"]
        text = row.get("job_text") or ""
        if not text and row.get("payload_json"):
            try:
                payload = json.loads(row["payload_json"])
                text = payload.get("text", "")
            except Exception:
                pass
        runs.append({
            "id": row["id"],
            "job_id": row["job_id"],
            "job_name": name,
            "text": text,
            "started_at_ms": row["started_at_ms"],
            "ended_at_ms": row.get("ended_at_ms"),
            "status": row.get("status"),
            "error": row.get("error"),
            "duration_ms": row.get("duration_ms"),
        })
    return {"runs": runs}


@router.get("/jobs")
async def list_cron_jobs(request: Request):
    jobs = await _runtime(request).list_jobs()
    return {"jobs": [_serialize_job(job) for job in jobs]}


@router.post("/jobs")
async def create_cron_job(body: CronJobCreateBody, request: Request):
    _ensure_supported_target(body.session_target)
    delivery = _build_delivery(
        _runtime(request),
        delivery_session_id=body.delivery_session_id if body.delivery_session_id is not None else _UNSET,
        notification_channels=body.notification_channels,
    )
    job = CronJob(
        name=body.name,
        description=body.description or None,
        schedule=_build_schedule(body.schedule_type, body.schedule_value, body.timezone),
        session_target=body.session_target,
        wake_mode=body.wake_mode,
        payload=SystemEventPayload(text=body.text),
        delivery=delivery,
        enabled=body.enabled,
        delete_after_run=body.delete_after_run,
    )
    created = await _runtime(request).add_job(job)
    return _serialize_job(created)


@router.get("/jobs/{job_id}")
async def get_cron_job(job_id: str, request: Request):
    job = await _runtime(request).get_job(job_id)
    if not job:
        raise HTTPException(404, "Cron job not found")
    return _serialize_job(job)


@router.put("/jobs/{job_id}")
async def update_cron_job(job_id: str, body: CronJobUpdateBody, request: Request):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "No cron job updates provided")
    _ensure_supported_target(updates.get("session_target"))

    existing_job = await _runtime(request).get_job(job_id)
    if not existing_job:
        raise HTTPException(404, "Cron job not found")

    runtime_updates: dict = {}
    for key in ("name", "description", "session_target", "wake_mode", "enabled", "delete_after_run"):
        if key in updates:
            runtime_updates[key] = updates[key]

    if "text" in updates:
        runtime_updates["payload"] = SystemEventPayload(text=updates["text"] or "")

    schedule_type = updates.get("schedule_type")
    schedule_value = updates.get("schedule_value")
    if schedule_type or schedule_value:
        if not schedule_type or schedule_value is None:
            raise HTTPException(400, "schedule_type and schedule_value must be updated together")
        runtime_updates["schedule"] = _build_schedule(schedule_type, schedule_value, updates.get("timezone"))

    if "delivery_session_id" in updates or "notification_channels" in updates:
        runtime_updates["delivery"] = _build_delivery(
            _runtime(request),
            delivery_session_id=updates["delivery_session_id"] if "delivery_session_id" in updates else _UNSET,
            notification_channels=updates.get(
                "notification_channels",
                existing_job.delivery.notification_channels if existing_job.delivery else None,
            ),
            existing=existing_job.delivery,
        )

    job = await _runtime(request).update_job(job_id, runtime_updates)
    return _serialize_job(job)


@router.delete("/jobs/{job_id}")
async def delete_cron_job(job_id: str, request: Request):
    removed = await _runtime(request).remove_job(job_id)
    if not removed:
        raise HTTPException(404, "Cron job not found")
    return {"success": True, "job_id": job_id}


@router.get("/jobs/{job_id}/runs")
async def list_cron_job_runs(job_id: str, request: Request, limit: int = 20):
    job = await _runtime(request).get_job(job_id)
    if not job:
        raise HTTPException(404, "Cron job not found")
    runs = await _runtime(request).list_runs(job_id, limit=limit)
    return {"runs": runs}


@router.post("/jobs/{job_id}/trigger")
async def trigger_cron_job(job_id: str, request: Request):
    runtime = _runtime(request)
    try:
        job = await runtime.trigger_job(job_id)
    except KeyError:
        raise HTTPException(404, "Cron job not found")
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))

    return {
        "success": True,
        "job_id": job_id,
        "deleted": job is None,
        "job": _serialize_job(job) if job else None,
    }
