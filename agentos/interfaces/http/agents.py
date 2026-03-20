"""
Agents API — 多 Agent CRUD + 偏好管理

支持多个 Agent 的创建/查询/更新/删除，向后兼容 default Agent。
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from agentos.capabilities.agents.config import AgentConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])

BUILTIN_SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"


# ── 辅助函数 ──────────────────────────────────────────


def _get_services(request: Request):
    return request.app.state.services


def _get_agent_registry(request: Request):
    return request.app.state.agent_registry


def _prefs_path(request: Request) -> Path:
    cfg = request.app.state.config
    home = Path(getattr(request.app.state, "agentos_home", "") or str(Path.home() / ".agentos"))
    return home / ".agent_preferences.json"


def _load_prefs(request: Request) -> dict:
    p = _prefs_path(request)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _save_prefs(request: Request, prefs: dict) -> None:
    p = _prefs_path(request)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(prefs, indent=2, ensure_ascii=False), encoding="utf-8")


def _build_agent_detail(agent_cfg: AgentConfig, request: Request) -> dict[str, Any]:
    """构建 Agent 的完整描述（含工具和技能详情）"""
    tool_registry = request.app.state.tool_registry
    skill_registry = request.app.state.skill_registry

    prefs = _load_prefs(request)
    tool_prefs = prefs.get("tools", {})
    skill_prefs = prefs.get("skills", {})

    tools_detail = []
    for name, tool in tool_registry._tools.items():
        # 如果 Agent 配置了 tools 列表，过滤展示
        if agent_cfg.tools and name not in agent_cfg.tools:
            continue
        enabled = tool_prefs.get(name, True)
        tools_detail.append({
            "name": name,
            "description": tool.description or "",
            "enabled": enabled,
        })

    skills_detail = []
    for skill in skill_registry.get_all():
        if agent_cfg.skills and skill.name not in agent_cfg.skills:
            continue
        enabled = skill_prefs.get(skill.name, True)
        # 分类: installed / builtin / workspace
        if skill.install_info:
            category = "installed"
        else:
            try:
                skill.path.resolve().relative_to(BUILTIN_SKILLS_DIR.resolve())
                category = "builtin"
            except ValueError:
                category = "workspace"
        skills_detail.append({
            "name": skill.name,
            "description": skill.description or "",
            "enabled": enabled,
            "category": category,
        })

    return {
        "id": agent_cfg.id,
        "name": agent_cfg.name,
        "status": "active" if agent_cfg.enabled else "disabled",
        "description": agent_cfg.description,
        "provider": agent_cfg.provider,
        "model": agent_cfg.model,
        "systemPrompt": agent_cfg.system_prompt,
        "temperature": agent_cfg.temperature,
        "maxTokens": agent_cfg.max_tokens,
        "toolCount": len(tools_detail),
        "skillCount": len(skills_detail),
        "tools": [t["name"] for t in tools_detail],
        "skills": [s["name"] for s in skills_detail],
        "toolsDetail": tools_detail,
        "skillsDetail": skills_detail,
        "canDelegateTo": agent_cfg.can_delegate_to,
        "maxDelegationDepth": agent_cfg.max_delegation_depth,
        "createdAt": agent_cfg.created_at,
        "updatedAt": agent_cfg.updated_at,
    }


# ── Pydantic 模型 ──────────────────────────────────────


class AgentPreferences(BaseModel):
    tools: dict[str, bool] | None = None
    skills: dict[str, bool] | None = None


class AgentConfigUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    systemPrompt: str | None = None
    tools: list[str] | None = None
    skills: list[str] | None = None
    can_delegate_to: list[str] | None = None
    max_delegation_depth: int | None = None


class AgentCreate(BaseModel):
    id: str
    name: str
    description: str = ""
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    system_prompt: str = ""
    tools: list[str] = []
    skills: list[str] = []
    can_delegate_to: list[str] = []
    max_delegation_depth: int = 3


# ── 路由 ──────────────────────────────────────────────


def _resolve_agent_id(session: dict[str, Any]) -> str:
    """从 session 记录中解析 agent_id（优先用列，回退 meta JSON）"""
    aid = session.get("agent_id")
    if aid and aid != "default":
        return aid
    meta_str = session.get("meta")
    if meta_str:
        try:
            meta = json.loads(meta_str) if isinstance(meta_str, str) else meta_str
            meta_aid = meta.get("agent_id")
            if meta_aid:
                return meta_aid
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass
    return aid or "default"


@router.get("")
async def list_agents(request: Request):
    """获取所有 Agents"""
    registry = _get_agent_registry(request)
    services = _get_services(request)
    sessions = await services.repo.list_sessions(limit=9999)

    result = []
    for agent_cfg in registry.list_all():
        agent = _build_agent_detail(agent_cfg, request)

        # 统计该 Agent 的会话数（兼容 agent_id 列与 meta JSON）
        agent_sessions = [s for s in sessions if _resolve_agent_id(s) == agent_cfg.id]
        agent["sessionCount"] = len(agent_sessions)

        if agent_sessions:
            latest = max(s.get("last_active", 0) for s in agent_sessions)
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

        result.append(agent)

    return result


@router.get("/{agent_id}")
async def get_agent(agent_id: str, request: Request):
    """获取 Agent 详情"""
    registry = _get_agent_registry(request)
    agent_cfg = registry.get(agent_id)
    if not agent_cfg:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    services = _get_services(request)
    agent = _build_agent_detail(agent_cfg, request)

    sessions = await services.repo.list_sessions(limit=9999)
    agent_sessions = [s for s in sessions if _resolve_agent_id(s) == agent_id]
    agent["sessionCount"] = len(agent_sessions)
    agent["sessions"] = [
        {
            "id": s["session_id"],
            "status": s.get("status", "active"),
            "channel": s.get("channel", "websocket"),
            "messageCount": s.get("message_count", 0),
            "startedAt": s.get("created_at", 0),
            "lastActive": s.get("last_active", 0),
        }
        for s in agent_sessions[:20]
    ]

    return agent


@router.post("")
async def create_agent(body: AgentCreate, request: Request):
    """创建新 Agent"""
    registry = _get_agent_registry(request)

    if registry.get(body.id):
        raise HTTPException(status_code=409, detail=f"Agent '{body.id}' already exists")

    # 从 default Agent 继承未指定的配置
    default = registry.get("default")
    agent = AgentConfig.create(
        id=body.id,
        name=body.name,
        description=body.description,
        provider=body.provider or (default.provider if default else "openai"),
        model=body.model or (default.model if default else "gpt-4o-mini"),
        temperature=body.temperature if body.temperature is not None else (default.temperature if default else 0.2),
        max_tokens=body.max_tokens,
        system_prompt=body.system_prompt,
        tools=body.tools,
        skills=body.skills,
        can_delegate_to=body.can_delegate_to,
        max_delegation_depth=body.max_delegation_depth,
    )
    registry.register(agent)

    # 初始化 per-agent workspace 目录（AGENTS.md / USER.md + workdir）
    from agentos.platform.config.workspace import ensure_agent_workspace
    agentos_home = getattr(request.app.state, "agentos_home", "") or str(Path.home() / ".agentos")
    await ensure_agent_workspace(agentos_home, agent.id)

    logger.info("Created agent: %s", agent.id)
    return _build_agent_detail(agent, request)


@router.put("/{agent_id}/config")
async def update_agent_config(agent_id: str, body: AgentConfigUpdate, request: Request):
    """更新 Agent 配置"""
    registry = _get_agent_registry(request)
    agent_cfg = registry.get(agent_id)
    if not agent_cfg:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    updates: dict[str, Any] = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.description is not None:
        updates["description"] = body.description
    if body.provider is not None:
        updates["provider"] = body.provider
    if body.model is not None:
        updates["model"] = body.model
    if body.temperature is not None:
        updates["temperature"] = body.temperature
    if body.max_tokens is not None:
        updates["max_tokens"] = body.max_tokens
    if body.systemPrompt is not None:
        updates["system_prompt"] = body.systemPrompt
    if body.tools is not None:
        updates["tools"] = body.tools
    if body.skills is not None:
        updates["skills"] = body.skills
    if body.can_delegate_to is not None:
        updates["can_delegate_to"] = body.can_delegate_to
    if body.max_delegation_depth is not None:
        updates["max_delegation_depth"] = body.max_delegation_depth

    updated = registry.update(agent_id, updates)
    logger.info("Agent config updated: %s -> %s", agent_id, list(updates.keys()))
    return _build_agent_detail(updated, request)


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, request: Request):
    """删除 Agent（不可删除 default）"""
    if agent_id == "default":
        raise HTTPException(status_code=400, detail="Cannot delete the default agent")

    registry = _get_agent_registry(request)
    if not registry.delete(agent_id):
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    logger.info("Deleted agent: %s", agent_id)
    return {"status": "deleted", "agent_id": agent_id}


@router.put("/{agent_id}/preferences")
async def update_agent_preferences(agent_id: str, body: AgentPreferences, request: Request):
    """批量更新 agent 的 tools/skills 启用偏好"""
    registry = _get_agent_registry(request)
    if not registry.get(agent_id):
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    prefs = _load_prefs(request)

    if body.tools is not None:
        prefs["tools"] = {**prefs.get("tools", {}), **body.tools}
    if body.skills is not None:
        prefs["skills"] = {**prefs.get("skills", {}), **body.skills}

    _save_prefs(request, prefs)
    logger.info("Agent preferences updated: tools=%s, skills=%s", body.tools, body.skills)
    return {"status": "saved"}
