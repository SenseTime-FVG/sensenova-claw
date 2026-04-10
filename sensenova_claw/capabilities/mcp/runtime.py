from __future__ import annotations

import asyncio
import json
import logging
import re
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, Any

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client

from sensenova_claw.capabilities.mcp.types import McpCatalog, McpServerConfig, McpToolDescriptor
from sensenova_claw.platform.config.mcp import build_mcp_servers_fingerprint, normalize_mcp_servers
from sensenova_claw.platform.config.config import config

if TYPE_CHECKING:
    from sensenova_claw.capabilities.agents.config import AgentConfig

logger = logging.getLogger(__name__)

_SAFE_NAME_PATTERN = re.compile(r"[^a-zA-Z0-9_]+")

_MCP_RECOVERABLE_ERROR_MARKERS = (
    "transport closed",
    "client closed",
    "connection closed",
    "broken pipe",
    "connection reset",
    "stream closed",
)


def sanitize_mcp_name(value: str) -> str:
    cleaned = _SAFE_NAME_PATTERN.sub("_", value.strip()).strip("_").lower()
    return cleaned or "mcp"


def build_safe_tool_name(server_name: str, tool_name: str) -> str:
    return f"mcp__{sanitize_mcp_name(server_name)}__{sanitize_mcp_name(tool_name)}"


def _normalize_input_schema(schema: Any) -> dict[str, Any] | None:
    if not isinstance(schema, dict):
        return None
    if schema.get("type") not in (None, "object"):
        return None
    normalized = dict(schema)
    normalized.setdefault("type", "object")
    normalized.setdefault("properties", {})
    normalized.setdefault("required", [])
    return normalized


def _normalize_mcp_result(content: list[Any], structured: Any, is_error: bool) -> dict[str, Any]:
    normalized_content: list[dict[str, Any]] = []
    for item in content:
        item_type = getattr(item, "type", None)
        if item_type == "text":
            normalized_content.append({"type": "text", "text": getattr(item, "text", "")})
            continue
        if item_type == "image":
            normalized_content.append(
                {"type": "image", "mimeType": getattr(item, "mimeType", ""), "data": getattr(item, "data", "")}
            )
            continue
        if item_type == "audio":
            normalized_content.append(
                {"type": "audio", "mimeType": getattr(item, "mimeType", ""), "data": getattr(item, "data", "")}
            )
            continue
        if item_type == "resource_link":
            normalized_content.append({"type": "resource_link", "name": getattr(item, "name", ""), "uri": getattr(item, "uri", "")})
            continue
        normalized_content.append({"type": item_type or "unknown", "value": str(item)})

    result: dict[str, Any] = {
        "content": normalized_content,
        "is_error": bool(is_error),
    }
    if structured is not None:
        result["structured_content"] = structured
    if not normalized_content and structured is not None:
        result["content"] = [{"type": "text", "text": json.dumps(structured, ensure_ascii=False, indent=2)}]
    return result


async def _open_client(server_cfg: McpServerConfig) -> tuple[AsyncExitStack, ClientSession]:
    stack = AsyncExitStack()
    try:
        if server_cfg.transport == "stdio":
            read_stream, write_stream = await stack.enter_async_context(
                stdio_client(
                    StdioServerParameters(
                        command=server_cfg.command,
                        args=list(server_cfg.args),
                        env=dict(server_cfg.env) or None,
                        cwd=server_cfg.cwd or None,
                    )
                )
            )
        elif server_cfg.transport == "streamable-http":
            read_stream, write_stream, _get_session_id = await stack.enter_async_context(
                streamablehttp_client(
                    server_cfg.url,
                    headers=dict(server_cfg.headers) or None,
                    timeout=server_cfg.timeout,
                )
            )
        else:
            read_stream, write_stream = await stack.enter_async_context(
                sse_client(
                    server_cfg.url,
                    headers=dict(server_cfg.headers) or None,
                    timeout=server_cfg.timeout,
                )
            )
        session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()
    except Exception:
        await stack.aclose()
        raise
    return stack, session


async def _list_tools(session: ClientSession) -> list[Any]:
    tools: list[Any] = []
    cursor: str | None = None
    while True:
        result = await session.list_tools(cursor=cursor)
        tools.extend(list(getattr(result, "tools", []) or []))
        cursor = getattr(result, "nextCursor", None)
        if not cursor:
            break
    return tools


def _tool_matches_selector(tool: McpToolDescriptor, selector: str) -> bool:
    normalized = selector.strip()
    if not normalized:
        return False
    aliases = {
        tool.safe_name,
        tool.tool_name,
        f"{tool.server_name}/{tool.tool_name}",
        f"{sanitize_mcp_name(tool.server_name)}/{sanitize_mcp_name(tool.tool_name)}",
        f"{tool.server_name}.{tool.tool_name}",
        f"{sanitize_mcp_name(tool.server_name)}.{sanitize_mcp_name(tool.tool_name)}",
    }
    return normalized in aliases


def _is_recoverable_mcp_transport_error(exc: Exception) -> bool:
    message = str(exc).strip().lower()
    if not message:
        return False
    return any(marker in message for marker in _MCP_RECOVERABLE_ERROR_MARKERS)


def is_mcp_server_enabled_for_agent(server_name: str, agent_config: AgentConfig | None) -> bool:
    if agent_config is None:
        return True
    if agent_config.mcp_servers is None:
        return False
    enabled_servers = {item for item in agent_config.mcp_servers if item}
    return not agent_config.mcp_servers or server_name in enabled_servers


def is_mcp_tool_enabled_for_agent(tool: McpToolDescriptor, agent_config: AgentConfig | None) -> bool:
    if not is_mcp_server_enabled_for_agent(tool.server_name, agent_config):
        return False
    if agent_config is None:
        return True
    if agent_config.mcp_tools is None:
        return False
    enabled_tools = [item for item in agent_config.mcp_tools if item]
    return not agent_config.mcp_tools or any(_tool_matches_selector(tool, selector) for selector in enabled_tools)


def filter_mcp_tools_for_agent(tools: list[McpToolDescriptor], agent_config: AgentConfig | None) -> list[McpToolDescriptor]:
    return [tool for tool in tools if is_mcp_tool_enabled_for_agent(tool, agent_config)]


class SharedStdioMcpServerRuntime:
    def __init__(self, server_cfg: McpServerConfig):
        self.server_cfg = server_cfg
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | Any | None = None
        self._connection_lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()
        self._tools_cache: list[Any] | None = None

    async def _ensure_connected(self) -> None:
        if self._session is not None:
            return
        async with self._connection_lock:
            if self._session is not None:
                return
            stack, session = await _open_client(self.server_cfg)
            self._stack = stack
            self._session = session

    async def list_tools(self) -> list[Any]:
        async with self._request_lock:
            if self._tools_cache is not None:
                return list(self._tools_cache)
            try:
                await self._ensure_connected()
                assert self._session is not None
                tools = await _list_tools(self._session)
                self._tools_cache = list(tools)
                return list(tools)
            except Exception:
                await self.close()
                raise

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        async with self._request_lock:
            try:
                await self._ensure_connected()
                assert self._session is not None
                return await self._session.call_tool(tool_name, arguments=arguments)
            except Exception:
                await self.close()
                raise

    async def close(self) -> None:
        async with self._connection_lock:
            stack = self._stack
            self._stack = None
            self._session = None
            self._tools_cache = None
            if stack is not None:
                await stack.aclose()


class McpServerRuntimePool:
    def __init__(self) -> None:
        self._stdio_runtimes: dict[str, SharedStdioMcpServerRuntime] = {}
        self._lock = asyncio.Lock()

    def _build_runtime_key(self, server_cfg: McpServerConfig) -> str:
        payload = {
            "name": server_cfg.name,
            "transport": server_cfg.transport,
            "timeout": server_cfg.timeout,
            "command": server_cfg.command,
            "args": list(server_cfg.args),
            "env": dict(server_cfg.env),
            "cwd": server_cfg.cwd,
        }
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)

    async def _create_stdio_runtime(self, server_cfg: McpServerConfig) -> SharedStdioMcpServerRuntime:
        return SharedStdioMcpServerRuntime(server_cfg)

    async def _get_or_create_stdio_runtime(self, server_cfg: McpServerConfig) -> SharedStdioMcpServerRuntime:
        key = self._build_runtime_key(server_cfg)
        existing = self._stdio_runtimes.get(key)
        if existing is not None:
            return existing
        async with self._lock:
            existing = self._stdio_runtimes.get(key)
            if existing is not None:
                return existing
            runtime = await self._create_stdio_runtime(server_cfg)
            self._stdio_runtimes[key] = runtime
            return runtime

    async def list_tools(self, server_cfg: McpServerConfig) -> list[Any]:
        runtime = await self._get_or_create_stdio_runtime(server_cfg)
        try:
            return await runtime.list_tools()
        except Exception as exc:  # noqa: BLE001
            if _is_recoverable_mcp_transport_error(exc):
                await self.invalidate(server_cfg)
            raise

    async def call_tool(self, server_cfg: McpServerConfig, tool_name: str, arguments: dict[str, Any]) -> Any:
        runtime = await self._get_or_create_stdio_runtime(server_cfg)
        try:
            return await runtime.call_tool(tool_name, arguments)
        except Exception as exc:  # noqa: BLE001
            if _is_recoverable_mcp_transport_error(exc):
                await self.invalidate(server_cfg)
            raise

    async def invalidate(self, server_cfg: McpServerConfig) -> None:
        key = self._build_runtime_key(server_cfg)
        async with self._lock:
            runtime = self._stdio_runtimes.pop(key, None)
        if runtime is not None:
            await runtime.close()


class SessionMcpRuntime:
    def __init__(
        self,
        session_id: str,
        servers: dict[str, McpServerConfig],
        shared_pool: McpServerRuntimePool | None = None,
    ):
        self.session_id = session_id
        self._servers = servers
        self._shared_pool = shared_pool
        self._catalog: McpCatalog | None = None
        self._catalog_lock = asyncio.Lock()

    async def ensure_catalog(self) -> McpCatalog:
        if self._catalog is not None:
            return self._catalog
        async with self._catalog_lock:
            if self._catalog is not None:
                return self._catalog
            tools: list[McpToolDescriptor] = []
            by_safe_name: dict[str, McpToolDescriptor] = {}
            for server_name, server_cfg in sorted(self._servers.items()):
                try:
                    listed = await self._list_tools_for_server(server_cfg)
                except Exception:  # noqa: BLE001
                    logger.warning("MCP server 初始化失败 session=%s server=%s", self.session_id, server_name, exc_info=True)
                    continue
                for tool in listed:
                    tool_name = str(getattr(tool, "name", "") or "").strip()
                    schema = _normalize_input_schema(getattr(tool, "inputSchema", None))
                    if not tool_name or schema is None:
                        logger.warning("跳过非法 MCP tool server=%s tool=%s", server_name, tool_name or "<empty>")
                        continue
                    safe_name = build_safe_tool_name(server_name, tool_name)
                    descriptor = McpToolDescriptor(
                        safe_name=safe_name,
                        server_name=server_name,
                        tool_name=tool_name,
                        title=getattr(tool, "title", None),
                        description=str(getattr(tool, "description", "") or f"MCP tool {tool_name}"),
                        input_schema=schema,
                    )
                    tools.append(descriptor)
                    by_safe_name[safe_name] = descriptor
            tools.sort(key=lambda item: (sanitize_mcp_name(item.server_name), item.tool_name, item.server_name))
            self._catalog = McpCatalog(tools=tools, by_safe_name=by_safe_name)
            logger.debug("MCP catalog ready session=%s tools=%s", self.session_id, [tool.safe_name for tool in tools])
            return self._catalog

    async def call_tool(self, safe_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        catalog = await self.ensure_catalog()
        descriptor = catalog.by_safe_name.get(safe_name)
        if descriptor is None:
            raise ValueError(f"未知 MCP 工具: {safe_name}")
        server_cfg = self._servers.get(descriptor.server_name)
        if server_cfg is None:
            raise RuntimeError(f"MCP server 未配置: {descriptor.server_name}")
        sanitized_args = {
            key: value
            for key, value in arguments.items()
            if not str(key).startswith("_")
        }
        logger.debug(
            "MCP call input session=%s server=%s tool=%s arguments=%s",
            self.session_id,
            descriptor.server_name,
            descriptor.tool_name,
            sanitized_args,
        )
        result = await self._call_tool_once(server_cfg, descriptor.tool_name, sanitized_args)
        return {
            "mcp_server": descriptor.server_name,
            "mcp_tool": descriptor.tool_name,
            **_normalize_mcp_result(
                content=list(getattr(result, "content", []) or []),
                structured=getattr(result, "structuredContent", None),
                is_error=bool(getattr(result, "isError", False)),
            ),
        }

    async def close(self) -> None:
        self._catalog = None

    async def _list_tools_for_server(self, server_cfg: McpServerConfig) -> list[Any]:
        if server_cfg.transport == "stdio" and self._shared_pool is not None:
            return await self._shared_pool.list_tools(server_cfg)
        stack, session = await _open_client(server_cfg)
        try:
            return await _list_tools(session)
        finally:
            await stack.aclose()

    async def _call_tool_once(
        self,
        server_cfg: McpServerConfig,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        if server_cfg.transport == "stdio" and self._shared_pool is not None:
            return await self._shared_pool.call_tool(server_cfg, tool_name, arguments)
        stack, session = await _open_client(server_cfg)
        try:
            return await session.call_tool(tool_name, arguments=arguments)
        finally:
            await stack.aclose()


class McpSessionManager:
    def __init__(self) -> None:
        self._runtimes: dict[str, SessionMcpRuntime] = {}
        self._fingerprints: dict[str, str] = {}
        self._shared_pool = McpServerRuntimePool()

    async def ensure_session(self, session_id: str) -> None:
        runtime = await self._get_or_create_runtime(session_id)
        await runtime.ensure_catalog()

    async def close_session(self, session_id: str) -> None:
        runtime = self._runtimes.pop(session_id, None)
        self._fingerprints.pop(session_id, None)
        if runtime is not None:
            await runtime.close()

    async def list_tools(self, session_id: str, agent_config: AgentConfig | None = None) -> list[McpToolDescriptor]:
        runtime = await self._get_or_create_runtime(session_id)
        catalog = await runtime.ensure_catalog()
        return filter_mcp_tools_for_agent(catalog.tools, agent_config)

    async def get_tool(self, session_id: str, safe_name: str) -> McpToolDescriptor | None:
        runtime = await self._get_or_create_runtime(session_id)
        catalog = await runtime.ensure_catalog()
        return catalog.by_safe_name.get(safe_name)

    async def call_tool(self, session_id: str, safe_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        runtime = await self._get_or_create_runtime(session_id)
        try:
            return await runtime.call_tool(safe_name, arguments)
        except Exception as exc:  # noqa: BLE001
            if _is_recoverable_mcp_transport_error(exc):
                logger.warning(
                    "MCP runtime broken, dropping session runtime session=%s error=%s",
                    session_id,
                    str(exc).strip() or type(exc).__name__,
                )
                await self.close_session(session_id)
            raise

    def get_cached_tools(self, session_id: str, agent_config: AgentConfig | None = None) -> list[McpToolDescriptor]:
        runtime = self._runtimes.get(session_id)
        if runtime is None or runtime._catalog is None:
            return []
        return filter_mcp_tools_for_agent(runtime._catalog.tools, agent_config)

    async def _get_or_create_runtime(self, session_id: str) -> SessionMcpRuntime:
        servers = normalize_mcp_servers(config.get("mcp.servers", {}))
        fingerprint = build_mcp_servers_fingerprint(servers)
        existing = self._runtimes.get(session_id)
        if existing is not None and self._fingerprints.get(session_id) == fingerprint:
            return existing
        if existing is not None:
            await existing.close()
        runtime = SessionMcpRuntime(session_id=session_id, servers=servers, shared_pool=self._shared_pool)
        self._runtimes[session_id] = runtime
        self._fingerprints[session_id] = fingerprint
        return runtime


class McpToolAdapter:
    """把 MCP tool 适配成现有 Tool 执行接口。"""

    risk_level = None

    def __init__(self, manager: McpSessionManager, descriptor: McpToolDescriptor):
        from sensenova_claw.capabilities.tools.base import ToolRiskLevel

        self.name = descriptor.safe_name
        self.description = descriptor.description
        self.parameters = descriptor.input_schema
        self.risk_level = ToolRiskLevel.LOW
        self._manager = manager
        self._descriptor = descriptor

    async def execute(self, **kwargs: Any) -> Any:
        session_id = str(kwargs.get("_session_id", "") or "").strip()
        if not session_id:
            raise ValueError("MCP 工具执行缺少 _session_id")
        return await self._manager.call_tool(
            session_id=session_id,
            safe_name=self._descriptor.safe_name,
            arguments=kwargs,
        )
