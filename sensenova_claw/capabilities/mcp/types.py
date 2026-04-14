from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


McpTransportType = Literal["stdio", "sse", "streamable-http"]


@dataclass(slots=True)
class McpServerConfig:
    name: str
    transport: McpTransportType
    timeout: float = 15.0
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: str = ""
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class McpToolDescriptor:
    safe_name: str
    server_name: str
    tool_name: str
    title: str | None
    description: str
    input_schema: dict[str, Any]


@dataclass(slots=True)
class McpCatalog:
    tools: list[McpToolDescriptor] = field(default_factory=list)
    by_safe_name: dict[str, McpToolDescriptor] = field(default_factory=dict)

