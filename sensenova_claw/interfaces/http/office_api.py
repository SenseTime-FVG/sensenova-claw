"""Office API。"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/office", tags=["office"])


def _get_services(request: Request):
    return request.app.state.services


def _get_agent_registry(request: Request):
    return request.app.state.agent_registry


def _build_idle_statuses(request: Request) -> dict[str, dict[str, str]]:
    statuses: dict[str, dict[str, str]] = {}
    for agent in _get_agent_registry(request).list_all():
        statuses[agent.id] = {"status": "idle"}
    return statuses


@router.get("/agent-status")
async def get_agent_status(request: Request) -> dict[str, Any]:
    """返回 office 页面使用的 agent 运行态。"""
    statuses = _build_idle_statuses(request)
    sessions = await _get_services(request).repo.list_sessions(limit=999999, include_hidden=True)

    for session in sessions:
        agent_id = str(session.get("agent_id") or "default")
        if agent_id not in statuses:
            statuses[agent_id] = {"status": "idle"}
        if str(session.get("last_turn_status") or "") == "started":
            statuses[agent_id] = {"status": "running"}

    return {
        "agents": statuses,
        "updated_at": int(time.time()),
    }
