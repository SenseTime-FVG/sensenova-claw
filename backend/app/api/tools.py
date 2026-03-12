"""
Tools API - 从真实 ToolRegistry 读取已注册的工具
"""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("")
async def list_tools(request: Request):
    """获取所有已注册的工具"""
    tool_registry = request.app.state.tool_registry
    tools = []
    for name, tool in tool_registry._tools.items():
        tools.append({
            "id": f"tool-{name}",
            "name": name,
            "description": tool.description or "",
            "category": "builtin",
            "version": "1.0.0",
            "enabled": True,
            "riskLevel": tool.risk_level.value if hasattr(tool.risk_level, "value") else "low",
            "parameters": tool.parameters or {},
        })
    return tools
