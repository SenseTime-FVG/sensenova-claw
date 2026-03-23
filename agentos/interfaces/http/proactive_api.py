"""Proactive REST API 端点。"""
from __future__ import annotations

import dataclasses
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/proactive", tags=["proactive"])


def _runtime(request: Request):
    return request.app.state.services.proactive_runtime


def _repo(request: Request):
    return request.app.state.services.repo


def _serialize_job(job) -> dict[str, Any]:
    """将 ProactiveJob 序列化为 dict。"""
    return {
        "id": job.id,
        "name": job.name,
        "agent_id": job.agent_id,
        "enabled": job.enabled,
        "source": job.source,
        "trigger": dataclasses.asdict(job.trigger),
        "task": dataclasses.asdict(job.task),
        "delivery": dataclasses.asdict(job.delivery),
        "safety": dataclasses.asdict(job.safety),
        "state": dataclasses.asdict(job.state),
    }


# ---------- Jobs ----------

@router.get("/jobs")
async def list_jobs(request: Request):
    """列出所有 proactive jobs。"""
    jobs = await _runtime(request).list_jobs()
    return {"jobs": [_serialize_job(j) for j in jobs]}


class CreateJobRequest(BaseModel):
    name: str
    agent_id: str = "proactive-agent"
    trigger: dict
    task: dict
    delivery: dict
    safety: dict | None = None
    enabled: bool = True


@router.post("/jobs")
async def create_job(body: CreateJobRequest, request: Request):
    """创建新的 proactive job。"""
    from agentos.kernel.proactive.models import (
        ConditionTrigger, DeliveryConfig, EventTrigger, JobState,
        ProactiveJob, ProactiveTask, SafetyConfig, TimeTrigger,
    )
    import uuid

    # 解析 trigger
    trigger_kind = body.trigger.get("kind", "time")
    if trigger_kind == "time":
        trigger = TimeTrigger(
            cron=body.trigger.get("cron"),
            every=body.trigger.get("every"),
            condition=body.trigger.get("condition"),
        )
    elif trigger_kind == "event":
        trigger = EventTrigger(
            event_type=body.trigger.get("event_type", ""),
            filter=body.trigger.get("filter"),
            debounce_ms=body.trigger.get("debounce_ms", 5000),
            condition=body.trigger.get("condition"),
        )
    elif trigger_kind == "condition":
        trigger = ConditionTrigger(
            check_interval=body.trigger.get("check_interval", "5m"),
            condition=body.trigger.get("condition", ""),
        )
    else:
        raise HTTPException(400, f"不支持的 trigger kind: {trigger_kind}")

    task = ProactiveTask(
        prompt=body.task.get("prompt", ""),
        use_memory=body.task.get("use_memory", False),
        system_prompt_override=body.task.get("system_prompt_override"),
    )

    delivery_data = body.delivery or {}
    delivery = DeliveryConfig(
        channels=delivery_data.get("channels", []),
        feishu_target=delivery_data.get("feishu_target"),
        summary_prompt=delivery_data.get("summary_prompt"),
    )

    safety_data = body.safety or {}
    safety = SafetyConfig(
        allowed_tools=safety_data.get("allowed_tools"),
        blocked_tools=safety_data.get("blocked_tools"),
        max_tool_calls=safety_data.get("max_tool_calls", 20),
        max_llm_calls=safety_data.get("max_llm_calls", 10),
        max_duration_ms=safety_data.get("max_duration_ms", 300_000),
        auto_disable_after_errors=safety_data.get("auto_disable_after_errors", 3),
    )

    job = ProactiveJob(
        id=f"pj_{uuid.uuid4().hex[:12]}",
        name=body.name,
        agent_id=body.agent_id,
        enabled=body.enabled,
        trigger=trigger,
        task=task,
        delivery=delivery,
        safety=safety,
        state=JobState(),
        source="api",
    )

    created = await _runtime(request).add_job(job)
    return _serialize_job(created)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request):
    """获取单个 proactive job 详情。"""
    jobs = {j.id: j for j in await _runtime(request).list_jobs()}
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Proactive job not found")
    return _serialize_job(job)


class JobUpdate(BaseModel):
    enabled: bool | None = None


@router.patch("/jobs/{job_id}")
async def update_job(job_id: str, body: JobUpdate, request: Request):
    """更新 proactive job（启用/禁用）。"""
    rt = _runtime(request)
    if body.enabled is not None:
        ok = await rt.set_job_enabled(job_id, body.enabled)
        if not ok:
            raise HTTPException(404, "Proactive job not found")
    return {"ok": True}


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str, request: Request):
    """删除 proactive job。"""
    removed = await _runtime(request).remove_job(job_id)
    if not removed:
        raise HTTPException(404, "Proactive job not found")
    return {"ok": True, "job_id": job_id}


# ---------- Runs ----------

@router.get("/runs")
async def list_runs(request: Request, job_id: str | None = None, limit: int = 50):
    """列出执行历史，可按 job_id 过滤。"""
    repo = _repo(request)
    if job_id:
        runs = await repo.list_proactive_runs(job_id, limit=limit)
    else:
        all_jobs = await _runtime(request).list_jobs()
        runs = []
        for job in all_jobs:
            runs.extend(await repo.list_proactive_runs(job.id, limit=10))
        runs.sort(key=lambda r: r.get("started_at_ms", 0), reverse=True)
        runs = runs[:limit]
    return {"runs": runs}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request):
    """获取单条执行记录详情。"""
    run = await _repo(request).get_proactive_run(run_id)
    if not run:
        raise HTTPException(404, "Proactive run not found")
    return run
