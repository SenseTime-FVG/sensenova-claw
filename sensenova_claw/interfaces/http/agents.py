"""
Agents API — 多 Agent CRUD + 偏好管理

支持多个 Agent 的创建/查询/更新/删除，向后兼容 default Agent。
"""
from __future__ import annotations

import json
import logging
import time
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from sensenova_claw.capabilities.agents.config import AgentConfig
from sensenova_claw.capabilities.agents.preferences import (
    load_preferences,
    save_preferences,
)
from sensenova_claw.capabilities.agents.registry import SYSTEM_PROMPT_FILENAME
from sensenova_claw.capabilities.mcp.runtime import (
    SessionMcpRuntime,
    is_mcp_server_enabled_for_agent,
    is_mcp_tool_enabled_for_agent,
)
from sensenova_claw.platform.config.mcp import normalize_mcp_servers
from sensenova_claw.capabilities.tools.registry import _is_tool_config_enabled
from sensenova_claw.platform.config.workspace import default_sensenova_claw_home

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])

BUILTIN_SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"


# ── 辅助函数 ──────────────────────────────────────────


def _get_services(request: Request):
    return request.app.state.services


def _get_agent_registry(request: Request):
    return request.app.state.agent_registry


def _get_config_manager(request: Request):
    return getattr(request.app.state, "config_manager", None)


def _sensenova_claw_home_path(request: Request) -> Path:
    return Path(getattr(request.app.state, "sensenova_claw_home", "") or default_sensenova_claw_home())


def _agent_prompt_path(request: Request, agent_id: str) -> Path:
    return _sensenova_claw_home_path(request) / "agents" / agent_id / SYSTEM_PROMPT_FILENAME


def _serialize_agent_for_config(agent: AgentConfig) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": agent.name,
        "description": agent.description,
        "model": agent.model,
        "temperature": agent.temperature,
        "tools": list(agent.tools),
        "skills": list(agent.skills),
        "mcp_servers": list(agent.mcp_servers),
        "mcp_tools": list(agent.mcp_tools),
        "workdir": agent.workdir,
        "can_delegate_to": list(agent.can_delegate_to) if agent.can_delegate_to is not None else None,
        "max_delegation_depth": agent.max_delegation_depth,
        "max_pingpong_turns": agent.max_pingpong_turns,
        "enabled": agent.enabled,
    }
    if agent.max_tokens is not None:
        data["max_tokens"] = agent.max_tokens
    return data


async def _persist_agent_record(
    request: Request,
    agent_id: str,
    agent: AgentConfig | None,
) -> None:
    config_manager = _get_config_manager(request)
    if config_manager is None:
        return

    raw_config = config_manager._load_raw_yaml()
    agents_section = deepcopy(raw_config.get("agents", {}))
    if not isinstance(agents_section, dict):
        agents_section = {}

    if agent is None:
        agents_section.pop(agent_id, None)
    else:
        agents_section[agent_id] = _serialize_agent_for_config(agent)

    await config_manager.replace("agents", agents_section)


def _persist_agent_prompt(request: Request, agent_id: str, system_prompt: str) -> None:
    prompt_path = _agent_prompt_path(request, agent_id)
    if system_prompt.strip():
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(system_prompt, encoding="utf-8")
    elif prompt_path.exists():
        prompt_path.unlink()


async def _build_agent_detail(
    agent_cfg: AgentConfig,
    request: Request,
    *,
    include_mcp_detail: bool = True,
) -> dict[str, Any]:
    """构建 Agent 的完整描述（含工具和技能详情）"""
    tool_registry = request.app.state.tool_registry
    skill_registry = request.app.state.skill_registry

    prefs = load_preferences(_sensenova_claw_home_path(request))
    skill_prefs = prefs.get("skills", {})

    tools_detail = []
    for name, tool in tool_registry._tools.items():
        if name == "send_message" and agent_cfg.can_delegate_to is None:
            continue
        # 如果 Agent 配置了 tools 列表，过滤展示
        if agent_cfg.tools and name not in agent_cfg.tools:
            continue
        enabled = _is_tool_config_enabled(name)
        tools_detail.append({
            "name": name,
            "description": tool.description or "",
            "enabled": enabled,
        })

    skills_detail = []
    for skill in skill_registry.get_all():
        # 显示所有技能，根据 Agent 配置决定 enabled 状态
        if agent_cfg.skills:
            enabled = skill.name in agent_cfg.skills
        else:
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

    mcp_servers_detail: list[dict[str, Any]] = []
    mcp_tools_detail: list[dict[str, Any]] = []
    mcp_servers = normalize_mcp_servers(getattr(request.app.state, "config").get("mcp.servers", {}))
    if include_mcp_detail and mcp_servers:
        runtime = SessionMcpRuntime(session_id=f"agent-detail:{agent_cfg.id}", servers=mcp_servers)
        try:
            catalog = await runtime.ensure_catalog()
            descriptors = catalog.tools
        except Exception:  # noqa: BLE001
            logger.warning("构建 Agent MCP 详情失败 agent=%s", agent_cfg.id, exc_info=True)
            descriptors = []
        finally:
            await runtime.close()
        descriptors_by_server: dict[str, list[Any]] = {}
        for descriptor in descriptors:
            descriptors_by_server.setdefault(descriptor.server_name, []).append(descriptor)
            mcp_tools_detail.append({
                "name": f"{descriptor.server_name}/{descriptor.tool_name}",
                "serverName": descriptor.server_name,
                "toolName": descriptor.tool_name,
                "safeName": descriptor.safe_name,
                "description": descriptor.description or "",
                "enabled": is_mcp_tool_enabled_for_agent(descriptor, agent_cfg),
            })
        for server_name, server_cfg in sorted(mcp_servers.items()):
            server_tools = descriptors_by_server.get(server_name, [])
            mcp_servers_detail.append({
                "name": server_name,
                "transport": server_cfg.transport,
                "enabled": is_mcp_server_enabled_for_agent(server_name, agent_cfg),
                "toolCount": len(server_tools),
            })

    payload = {
        "id": agent_cfg.id,
        "name": agent_cfg.name,
        "status": "active" if agent_cfg.enabled else "disabled",
        "description": agent_cfg.description,
        "model": agent_cfg.model,
        "systemPrompt": agent_cfg.system_prompt,
        "temperature": agent_cfg.temperature,
        "maxTokens": agent_cfg.max_tokens,
        "toolCount": sum(1 for t in tools_detail if t["enabled"]),
        "skillCount": sum(1 for s in skills_detail if s["enabled"]),
        "mcpServerCount": sum(1 for s in mcp_servers_detail if s["enabled"]),
        "mcpToolCount": sum(1 for t in mcp_tools_detail if t["enabled"]),
        "tools": [t["name"] for t in tools_detail if t["enabled"]],
        "skills": [s["name"] for s in skills_detail if s["enabled"]],
        "mcpServers": [s["name"] for s in mcp_servers_detail if s["enabled"]],
        "mcpTools": [t["name"] for t in mcp_tools_detail if t["enabled"]],
        "toolsDetail": tools_detail,
        "skillsDetail": skills_detail,
        "canDelegateTo": agent_cfg.can_delegate_to,
        "maxDelegationDepth": agent_cfg.max_delegation_depth,
        "createdAt": agent_cfg.created_at,
        "updatedAt": agent_cfg.updated_at,
    }
    if include_mcp_detail:
        payload["mcpServersDetail"] = mcp_servers_detail
        payload["mcpToolsDetail"] = mcp_tools_detail
    return payload


# ── Pydantic 模型 ──────────────────────────────────────


class AgentPreferences(BaseModel):
    tools: dict[str, bool] | None = None
    skills: dict[str, bool] | None = None


class AgentConfigUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    systemPrompt: str | None = None
    tools: list[str] | None = None
    skills: list[str] | None = None
    mcp_servers: list[str] | None = None
    mcp_tools: list[str] | None = None
    can_delegate_to: list[str] | None = None
    max_delegation_depth: int | None = None


class AgentCreate(BaseModel):
    id: str
    name: str
    description: str = ""
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    system_prompt: str = ""
    tools: list[str] = []
    skills: list[str] = []
    mcp_servers: list[str] = []
    mcp_tools: list[str] = []
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
        agent = await _build_agent_detail(agent_cfg, request, include_mcp_detail=False)

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
    agent = await _build_agent_detail(agent_cfg, request)

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
        model=body.model or (default.model if default else "gpt-4o-mini"),
        temperature=body.temperature if body.temperature is not None else (default.temperature if default else 1.0),
        max_tokens=body.max_tokens,
        system_prompt=body.system_prompt,
        tools=body.tools,
        skills=body.skills,
        mcp_servers=body.mcp_servers,
        mcp_tools=body.mcp_tools,
        can_delegate_to=body.can_delegate_to,
        max_delegation_depth=body.max_delegation_depth,
    )
    # 初始化 per-agent workspace 目录（AGENTS.md / USER.md + workdir）
    from sensenova_claw.platform.config.workspace import ensure_agent_workspace
    await ensure_agent_workspace(str(_sensenova_claw_home_path(request)), agent.id)
    _persist_agent_prompt(request, agent.id, agent.system_prompt)
    await _persist_agent_record(request, agent.id, agent)
    registry.register(agent)

    logger.info("Created agent: %s", agent.id)
    return await _build_agent_detail(agent, request)


@router.put("/{agent_id}/config")
async def update_agent_config(agent_id: str, body: AgentConfigUpdate, request: Request):
    """更新 Agent 配置"""
    registry = _get_agent_registry(request)
    agent_cfg = registry.get(agent_id)
    if not agent_cfg:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    provided_fields = body.model_dump(exclude_unset=True)
    updates: dict[str, Any] = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.description is not None:
        updates["description"] = body.description
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
    if body.mcp_servers is not None:
        updates["mcp_servers"] = body.mcp_servers
    if body.mcp_tools is not None:
        updates["mcp_tools"] = body.mcp_tools
    if "can_delegate_to" in provided_fields:
        updates["can_delegate_to"] = body.can_delegate_to
    if body.max_delegation_depth is not None:
        updates["max_delegation_depth"] = body.max_delegation_depth

    updated = replace(agent_cfg, **updates, updated_at=time.time())
    _persist_agent_prompt(request, agent_id, updated.system_prompt)
    await _persist_agent_record(request, agent_id, updated)
    registry.register(updated)
    logger.info("Agent config updated: %s -> %s", agent_id, list(updates.keys()))
    return await _build_agent_detail(updated, request)


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, request: Request):
    """删除 Agent（不可删除 default）"""
    if agent_id == "default":
        raise HTTPException(status_code=400, detail="Cannot delete the default agent")

    registry = _get_agent_registry(request)
    if not registry.get(agent_id):
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    await _persist_agent_record(request, agent_id, None)
    _persist_agent_prompt(request, agent_id, "")
    registry.delete(agent_id)

    logger.info("Deleted agent: %s", agent_id)
    return {"status": "deleted", "agent_id": agent_id}


@router.put("/{agent_id}/preferences")
async def update_agent_preferences(agent_id: str, body: AgentPreferences, request: Request):
    """批量更新 agent 的 tools/skills 启用偏好

    注意：tools 开关已迁移到 config.yml，此端点仅保留对 skills 偏好的写入。
    tools 字段如果传入将被忽略（应通过 PUT /api/tools/{name}/enabled 或 Agent 配置管理）。
    """
    registry = _get_agent_registry(request)
    if not registry.get(agent_id):
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    home = _sensenova_claw_home_path(request)

    if body.skills is not None:
        prefs = load_preferences(home)
        prefs["skills"] = {**prefs.get("skills", {}), **body.skills}
        save_preferences(home, prefs)

    logger.info("Agent preferences updated: skills=%s (tools ignored, use config.yml)", body.skills)
    return {"status": "saved"}
