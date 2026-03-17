"""
Tools API - 从真实 ToolRegistry 读取已注册的工具，支持启用/禁用
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tools", tags=["tools"])


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


class EnablePayload(BaseModel):
    enabled: bool


@router.get("")
async def list_tools(request: Request):
    """获取所有已注册的工具"""
    tool_registry = request.app.state.tool_registry
    prefs = _load_prefs(request)
    tool_prefs = prefs.get("tools", {})

    tools = []
    for name, tool in tool_registry._tools.items():
        enabled = tool_prefs.get(name, True)
        tools.append({
            "id": f"tool-{name}",
            "name": name,
            "description": tool.description or "",
            "category": "builtin",
            "version": "1.0.0",
            "enabled": enabled,
            "riskLevel": tool.risk_level.value if hasattr(tool.risk_level, "value") else "low",
            "parameters": tool.parameters or {},
        })
    return tools


@router.put("/{tool_name}/enabled")
async def toggle_tool(tool_name: str, body: EnablePayload, request: Request):
    """启用/禁用工具"""
    tool_registry = request.app.state.tool_registry
    tool = tool_registry.get(tool_name)
    if not tool:
        raise HTTPException(404, f"Tool 不存在: {tool_name}")

    prefs = _load_prefs(request)
    if "tools" not in prefs:
        prefs["tools"] = {}
    prefs["tools"][tool_name] = body.enabled
    _save_prefs(request, prefs)

    logger.info("Tool %s %s", tool_name, "enabled" if body.enabled else "disabled")
    return {"name": tool_name, "enabled": body.enabled}
