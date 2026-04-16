from __future__ import annotations

import hashlib
import json
from typing import Any

from sensenova_claw.capabilities.mcp.types import McpServerConfig


def normalize_mcp_servers(value: Any) -> dict[str, McpServerConfig]:
    """将 config 中的 mcp.servers 归一化为运行时可消费结构。"""
    if not isinstance(value, dict):
        return {}

    servers: dict[str, McpServerConfig] = {}
    for server_name, raw in value.items():
        if not isinstance(server_name, str) or not server_name.strip():
            continue
        if not isinstance(raw, dict):
            continue

        transport = str(raw.get("transport") or "").strip().lower()
        if not transport:
            transport = "stdio" if raw.get("command") else "sse"
        if transport not in {"stdio", "sse", "streamable-http"}:
            continue

        timeout = float(raw.get("timeout", 15) or 15)
        args = raw.get("args", [])
        env = raw.get("env", {})
        headers = raw.get("headers", {})
        servers[server_name] = McpServerConfig(
            name=server_name,
            transport=transport,  # type: ignore[arg-type]
            timeout=timeout,
            command=str(raw.get("command", "") or ""),
            args=[str(item) for item in args] if isinstance(args, list) else [],
            env={str(k): str(v) for k, v in env.items()} if isinstance(env, dict) else {},
            cwd=str(raw.get("cwd", "") or ""),
            url=str(raw.get("url", "") or ""),
            headers={str(k): str(v) for k, v in headers.items()} if isinstance(headers, dict) else {},
        )
    return servers


def build_mcp_servers_fingerprint(servers: dict[str, McpServerConfig]) -> str:
    serializable = {
        name: {
            "transport": server.transport,
            "timeout": server.timeout,
            "command": server.command,
            "args": list(server.args),
            "env": dict(server.env),
            "cwd": server.cwd,
            "url": server.url,
            "headers": dict(server.headers),
        }
        for name, server in sorted(servers.items())
    }
    raw = json.dumps(serializable, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()

