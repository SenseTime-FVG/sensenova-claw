from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from sensenova_claw.capabilities.agents.config import AgentConfig
from sensenova_claw.capabilities.mcp.runtime import (
    McpServerRuntimePool,
    McpSessionManager,
    SessionMcpRuntime,
    SharedStdioMcpServerRuntime,
    build_safe_tool_name,
    filter_mcp_tools_for_agent,
)
from sensenova_claw.platform.config.config import config
from sensenova_claw.platform.config.mcp import build_mcp_servers_fingerprint, normalize_mcp_servers


def _write_probe_server(tmp_path: Path) -> Path:
    script_path = tmp_path / "mcp_probe_server.py"
    script_path.write_text(
        """
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("probe")

@mcp.tool()
def echo_probe(text: str) -> str:
    return f"MCP_ECHO:{text}"

if __name__ == "__main__":
    mcp.run("stdio")
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return script_path


class TestMcpConfig:
    def test_normalize_stdio_server(self):
        servers = normalize_mcp_servers(
            {
                "probe": {
                    "transport": "stdio",
                    "command": sys.executable,
                    "args": ["server.py"],
                    "env": {"TOKEN": "abc"},
                    "cwd": "/tmp/demo",
                    "timeout": 12,
                }
            }
        )
        assert servers["probe"].transport == "stdio"
        assert servers["probe"].command == sys.executable
        assert servers["probe"].args == ["server.py"]
        assert servers["probe"].env["TOKEN"] == "abc"
        assert servers["probe"].cwd == "/tmp/demo"
        assert servers["probe"].timeout == 12

    def test_fingerprint_changes_when_config_changes(self):
        servers_a = normalize_mcp_servers({"probe": {"command": "python3", "args": ["a.py"]}})
        servers_b = normalize_mcp_servers({"probe": {"command": "python3", "args": ["b.py"]}})
        assert build_mcp_servers_fingerprint(servers_a) != build_mcp_servers_fingerprint(servers_b)


class TestMcpRuntime:
    @pytest.mark.asyncio
    async def test_session_manager_loads_stdio_catalog_and_calls_tool(self, tmp_path: Path):
        server_script = _write_probe_server(tmp_path)
        original = config.get("mcp.servers", {})
        config.set(
            "mcp.servers",
            {
                "probe": {
                    "transport": "stdio",
                    "command": sys.executable,
                    "args": [str(server_script)],
                    "timeout": 5,
                }
            },
        )
        manager = McpSessionManager()
        safe_name = build_safe_tool_name("probe", "echo_probe")
        try:
            await manager.ensure_session("s1")
            tools = manager.get_cached_tools("s1")
            assert [tool.safe_name for tool in tools] == [safe_name]

            result = await manager.call_tool("s1", safe_name, {"text": "hello"})
            assert result["mcp_server"] == "probe"
            assert result["mcp_tool"] == "echo_probe"
            assert result["content"][0]["text"] == "MCP_ECHO:hello"
        finally:
            await manager.close_session("s1")
            config.set("mcp.servers", original)

    @pytest.mark.asyncio
    async def test_filter_tools_for_agent_policy(self):
        tool_a = type("ToolA", (), {"safe_name": "mcp__docs__search", "server_name": "docs", "tool_name": "search"})()
        tool_a2 = type("ToolA2", (), {"safe_name": "mcp__docs__fetch", "server_name": "docs", "tool_name": "fetch"})()
        tool_b = type("ToolB", (), {"safe_name": "mcp__ops__restart", "server_name": "ops", "tool_name": "restart"})()
        agent = AgentConfig(
            id="a",
            name="A",
            mcp_servers=["docs"],
            mcp_tools=["docs/search"],
        )
        filtered = filter_mcp_tools_for_agent([tool_a, tool_a2, tool_b], agent)  # type: ignore[arg-type]
        assert filtered == [tool_a]

    @pytest.mark.asyncio
    async def test_filter_tools_for_agent_tri_state_policy(self):
        tool_a = type("ToolA", (), {"safe_name": "mcp__docs__search", "server_name": "docs", "tool_name": "search"})()
        tool_b = type("ToolB", (), {"safe_name": "mcp__ops__restart", "server_name": "ops", "tool_name": "restart"})()

        disabled_agent = AgentConfig(id="a", name="A", mcp_servers=None, mcp_tools=None)
        assert filter_mcp_tools_for_agent([tool_a, tool_b], disabled_agent) == []  # type: ignore[arg-type]

        enabled_agent = AgentConfig(id="b", name="B", mcp_servers=[], mcp_tools=[])
        assert filter_mcp_tools_for_agent([tool_a, tool_b], enabled_agent) == [tool_a, tool_b]  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_call_tool_discards_broken_runtime_after_transport_closed(self, monkeypatch):
        original = config.get("mcp.servers", {})
        config.set("mcp.servers", {"probe": {"command": sys.executable, "args": ["noop.py"]}})
        manager = McpSessionManager()
        safe_name = build_safe_tool_name("probe", "echo_probe")

        class _BrokenRuntime:
            def __init__(self):
                self.closed = False

            async def call_tool(self, _safe_name, _arguments):
                raise RuntimeError("Transport closed")

            async def close(self):
                self.closed = True

        class _HealthyRuntime:
            def __init__(self):
                self.closed = False

            async def call_tool(self, _safe_name, arguments):
                return {"mcp_server": "probe", "mcp_tool": "echo_probe", "content": [{"type": "text", "text": arguments["text"]}], "is_error": False}

            async def close(self):
                self.closed = True

        broken = _BrokenRuntime()
        healthy = _HealthyRuntime()
        runtimes = [broken, healthy]

        async def fake_get_or_create(session_id):  # type: ignore[no-untyped-def]
            assert session_id == "s1"
            runtime = manager._runtimes.get(session_id)
            if runtime is not None:
                return runtime
            runtime = runtimes.pop(0)
            manager._runtimes[session_id] = runtime  # type: ignore[assignment]
            manager._fingerprints[session_id] = "fp"
            return runtime

        monkeypatch.setattr(manager, "_get_or_create_runtime", fake_get_or_create)
        try:
            with pytest.raises(RuntimeError, match="Transport closed"):
                await manager.call_tool("s1", safe_name, {"text": "hello"})

            assert broken.closed is True
            assert "s1" not in manager._runtimes
            assert "s1" not in manager._fingerprints

            result = await manager.call_tool("s1", safe_name, {"text": "world"})
            assert result["content"][0]["text"] == "world"
        finally:
            config.set("mcp.servers", original)

    @pytest.mark.asyncio
    async def test_shared_stdio_runtime_serializes_tool_calls(self, monkeypatch):
        server_cfg = normalize_mcp_servers({"browsermcp": {"command": sys.executable, "args": ["noop.py"]}})["browsermcp"]
        runtime = SharedStdioMcpServerRuntime(server_cfg)

        active = 0
        max_active = 0

        class _FakeSession:
            async def call_tool(self, _tool_name, arguments):  # type: ignore[no-untyped-def]
                nonlocal active, max_active
                active += 1
                max_active = max(max_active, active)
                await asyncio.sleep(0.05)
                active -= 1
                return type("Result", (), {"content": [type("Text", (), {"type": "text", "text": arguments["text"]})()], "structuredContent": None, "isError": False})()

        async def fake_ensure_connected():  # type: ignore[no-untyped-def]
            runtime._session = _FakeSession()  # type: ignore[assignment]

        monkeypatch.setattr(runtime, "_ensure_connected", fake_ensure_connected)

        await asyncio.gather(
            runtime.call_tool("echo_probe", {"text": "a"}),
            runtime.call_tool("echo_probe", {"text": "b"}),
        )
        assert max_active == 1

    @pytest.mark.asyncio
    async def test_stdio_catalog_is_shared_across_sessions(self, monkeypatch):
        servers = normalize_mcp_servers({"probe": {"command": sys.executable, "args": ["noop.py"]}})
        pool = McpServerRuntimePool()
        runtime_a = SessionMcpRuntime(session_id="s1", servers=servers, shared_pool=pool)
        runtime_b = SessionMcpRuntime(session_id="s2", servers=servers, shared_pool=pool)

        calls = {"count": 0}

        class _FakeSharedRuntime:
            def __init__(self):
                self._cache = None

            async def list_tools(self):  # type: ignore[no-untyped-def]
                if self._cache is not None:
                    return list(self._cache)
                calls["count"] += 1
                self._cache = [
                    type(
                        "Tool",
                        (),
                        {
                            "name": "echo_probe",
                            "title": None,
                            "description": "Echo probe",
                            "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
                        },
                    )()
                ]
                return list(self._cache)

            async def close(self):  # type: ignore[no-untyped-def]
                return None

        async def fake_create(_server_cfg):  # type: ignore[no-untyped-def]
            return _FakeSharedRuntime()

        monkeypatch.setattr(pool, "_create_stdio_runtime", fake_create)

        catalog_a = await runtime_a.ensure_catalog()
        catalog_b = await runtime_b.ensure_catalog()

        assert calls["count"] == 1
        assert [tool.safe_name for tool in catalog_a.tools] == ["mcp__probe__echo_probe"]
        assert [tool.safe_name for tool in catalog_b.tools] == ["mcp__probe__echo_probe"]
