"""
Agents API - 从真实 config / registries / repo 读取 agent 信息
"""
from __future__ import annotations

import time
from fastapi import APIRouter, Request, HTTPException
from typing import Any

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _get_services(request: Request):
    return request.app.state.services


def _build_default_agent(request: Request) -> dict[str, Any]:
    """构建 default agent 的完整描述（从真实 config 和 registry 读取）"""
    cfg = request.app.state.config
    tool_registry = request.app.state.tool_registry
    skill_registry = request.app.state.skill_registry

    provider = cfg.get("agent.provider", "mock")
    model = cfg.get("agent.default_model", "mock-agent-v1")
    system_prompt = cfg.get("agent.system_prompt", "")
    temperature = cfg.get("agent.default_temperature", 0.2)

    tool_names = list(tool_registry._tools.keys())
    skill_names = [s.name for s in skill_registry.get_all()]

    return {
        "id": "default",
        "name": "Default Agent",
        "status": "active",
        "description": f"默认 AI Agent ({provider}/{model})",
        "provider": provider,
        "model": model,
        "systemPrompt": system_prompt,
        "temperature": temperature,
        "toolCount": len(tool_names),
        "skillCount": len(skill_names),
        "tools": tool_names,
        "skills": skill_names,
    }


@router.get("")
async def list_agents(request: Request):
    """获取所有 Agents（目前仅 default agent）"""
    services = _get_services(request)
    agent = _build_default_agent(request)

    # 从 DB 查询真实 session 数量
    sessions = await services.repo.list_sessions(limit=9999)
    agent["sessionCount"] = len(sessions)

    # 计算 lastActive
    if sessions:
        latest = max(s.get("last_active", 0) for s in sessions)
        delta = time.time() - latest
        if delta < 60:
            agent["lastActive"] = f"{int(delta)} seconds ago"
        elif delta < 3600:
            agent["lastActive"] = f"{int(delta / 60)} minutes ago"
        elif delta < 86400:
            agent["lastActive"] = f"{int(delta / 3600)} hours ago"
        else:
            agent["lastActive"] = f"{int(delta / 86400)} days ago"
    else:
        agent["lastActive"] = "never"

    return [agent]


@router.get("/{agent_id}")
async def get_agent(agent_id: str, request: Request):
    """获取 Agent 详情"""
    if agent_id != "default":
        raise HTTPException(status_code=404, detail="Agent not found")

    services = _get_services(request)
    agent = _build_default_agent(request)

    sessions = await services.repo.list_sessions(limit=9999)
    agent["sessionCount"] = len(sessions)
    agent["sessions"] = [
        {
            "id": s["session_id"],
            "status": s.get("status", "active"),
            "channel": s.get("channel", "websocket"),
            "messageCount": s.get("message_count", 0),
            "startedAt": s.get("created_at", 0),
            "lastActive": s.get("last_active", 0),
        }
        for s in sessions[:20]
    ]

    return agent
