"""MCP API - 管理全局 mcp.servers 配置。"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from sensenova_claw.platform.config.mcp import normalize_mcp_servers

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class KeyValueItem(BaseModel):
    key: str = ""
    value: str = ""


class McpServerBody(BaseModel):
    name: str
    transport: Literal["stdio", "sse", "streamable-http"] = "stdio"
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: list[KeyValueItem] = Field(default_factory=list)
    cwd: str = ""
    url: str = ""
    headers: list[KeyValueItem] = Field(default_factory=list)
    timeout: float = 15


class McpServersUpdateBody(BaseModel):
    servers: list[McpServerBody] = Field(default_factory=list)


def _pairs_to_dict(items: list[KeyValueItem]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        key = item.key.strip()
        if not key:
            continue
        result[key] = item.value
    return result


def _dict_to_pairs(data: dict[str, Any]) -> list[dict[str, str]]:
    return [{"key": str(key), "value": str(value)} for key, value in data.items()]


def _normalize_server_payload(raw_name: str, raw: dict[str, Any]) -> dict[str, Any]:
    server = normalize_mcp_servers({raw_name: raw}).get(raw_name)
    if server is None:
        raise HTTPException(400, f"非法 MCP transport: {raw.get('transport')}")
    if server.transport == "stdio" and not server.command:
        raise HTTPException(400, f"MCP server `{raw_name}` 缺少 command")
    if server.transport in {"sse", "streamable-http"} and not server.url:
        raise HTTPException(400, f"MCP server `{raw_name}` 缺少 url")
    if server.timeout <= 0:
        raise HTTPException(400, f"MCP server `{raw_name}` 的 timeout 必须大于 0")
    return {
        "transport": server.transport,
        "command": server.command,
        "args": list(server.args),
        "env": dict(server.env),
        "cwd": server.cwd,
        "url": server.url,
        "headers": dict(server.headers),
        "timeout": server.timeout,
    }


def _serialize_servers(config_value: Any) -> list[dict[str, Any]]:
    servers = normalize_mcp_servers(config_value)
    serialized: list[dict[str, Any]] = []
    for name, server in sorted(servers.items()):
        serialized.append(
            {
                "name": name,
                "transport": server.transport,
                "command": server.command,
                "args": list(server.args),
                "env": _dict_to_pairs(server.env),
                "cwd": server.cwd,
                "url": server.url,
                "headers": _dict_to_pairs(server.headers),
                "timeout": server.timeout,
            }
        )
    return serialized


@router.get("/servers")
async def list_mcp_servers(request: Request):
    cfg = request.app.state.config
    return {"servers": _serialize_servers(cfg.get("mcp.servers", {}))}


@router.put("/servers")
async def save_mcp_servers(body: McpServersUpdateBody, request: Request):
    next_servers: dict[str, dict[str, Any]] = {}
    used_names: set[str] = set()

    for item in body.servers:
        name = item.name.strip()
        if not name:
            raise HTTPException(400, "MCP server 名称不能为空")
        if name in used_names:
            raise HTTPException(400, f"MCP server 名称重复: {name}")
        used_names.add(name)

        raw = {
            "transport": item.transport,
            "command": item.command,
            "args": list(item.args),
            "env": _pairs_to_dict(item.env),
            "cwd": item.cwd,
            "url": item.url,
            "headers": _pairs_to_dict(item.headers),
            "timeout": item.timeout,
        }
        next_servers[name] = _normalize_server_payload(name, raw)

    config_manager = request.app.state.config_manager
    section = await config_manager.update("mcp", {"servers": next_servers})
    return {"servers": _serialize_servers(section.get("servers", {}))}
