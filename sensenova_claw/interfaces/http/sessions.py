"""Sessions API。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from sensenova_claw.adapters.storage.session_jsonl import SessionJsonlWriter
from sensenova_claw.platform.config.workspace import default_sensenova_claw_home

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _get_services(request: Request):
    return request.app.state.services


def _get_sensenova_claw_home(request: Request) -> Path:
    return Path(getattr(request.app.state, "sensenova_claw_home", "") or default_sensenova_claw_home())


class SessionFilter(BaseModel):
    search_term: str = ""
    status: str = "all"


class BulkDeleteRequest(BaseModel):
    session_ids: list[str] = Field(default_factory=list)
    filter: SessionFilter | None = None


def _parse_title(meta: str | None) -> str:
    if not meta:
        return ""
    try:
        obj = json.loads(meta)
    except (json.JSONDecodeError, TypeError):
        return ""
    return str(obj.get("title") or obj.get("name") or "")


def _match_session(session: dict, session_filter: SessionFilter) -> bool:
    search_term = session_filter.search_term.strip().lower()
    status = session_filter.status.strip().lower()

    if status and status != "all" and str(session.get("status", "")).lower() != status:
        return False
    if not search_term:
        return True

    title = _parse_title(session.get("meta")).lower()
    session_id = str(session.get("session_id", "")).lower()
    return search_term in title or search_term in session_id


async def _delete_session_record(request: Request, session: dict) -> str:
    services = _get_services(request)
    session_id = str(session["session_id"])
    agent_id = str(session.get("agent_id") or "default")

    meta = await services.repo.get_session_meta(session_id)
    if meta and meta.get("agent_id"):
        agent_id = str(meta["agent_id"])

    await services.gateway.delete_session(session_id)

    jsonl_writer = SessionJsonlWriter(base_dir=_get_sensenova_claw_home(request) / "agents")
    jsonl_writer.delete_session_file(agent_id, session_id)
    return session_id


@router.get("")
async def list_sessions(request: Request, include_hidden: bool = Query(default=False)):
    """获取会话列表。"""
    sessions = await _get_services(request).gateway.list_sessions(include_hidden=include_hidden)
    return JSONResponse(content={"sessions": sessions})


@router.get("/{session_id}/turns")
async def get_session_turns(session_id: str, request: Request):
    """获取会话的所有轮次。"""
    turns = await _get_services(request).gateway.get_session_turns(session_id)
    return JSONResponse(content={"turns": turns})


@router.get("/{session_id}/events")
async def get_session_events(session_id: str, request: Request):
    """获取会话的所有事件。"""
    events = await _get_services(request).gateway.get_session_events(session_id)
    return JSONResponse(content={"events": events})


@router.get("/{session_id}/messages")
async def list_session_messages(session_id: str, request: Request):
    """获取会话的所有消息。"""
    messages = await _get_services(request).gateway.get_messages(session_id)
    return JSONResponse(content={"messages": messages})


@router.delete("/{session_id}")
async def delete_session(session_id: str, request: Request):
    """强制删除会话及其 JSONL 文件。"""
    sessions = await _get_services(request).repo.list_sessions(limit=9999, include_hidden=True)
    session = next((item for item in sessions if item["session_id"] == session_id), None)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    await _delete_session_record(request, session)

    return {"status": "deleted", "session_id": session_id}


@router.post("/bulk-delete")
async def bulk_delete_sessions(body: BulkDeleteRequest, request: Request):
    """按显式 session 列表或筛选条件批量删除会话。"""
    sessions = await _get_services(request).repo.list_sessions(limit=999999, include_hidden=True)

    if body.session_ids:
        session_id_set = set(body.session_ids)
        targets = [session for session in sessions if session["session_id"] in session_id_set]
    elif body.filter is not None:
        targets = [session for session in sessions if _match_session(session, body.filter)]
    else:
        raise HTTPException(status_code=400, detail="session_ids or filter is required")

    deleted_ids: list[str] = []
    for session in targets:
        deleted_ids.append(await _delete_session_record(request, session))

    return {
        "status": "deleted",
        "deleted_count": len(deleted_ids),
        "deleted_session_ids": deleted_ids,
    }
