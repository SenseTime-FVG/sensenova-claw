from __future__ import annotations

import sys
from pathlib import Path

import pytest

from sensenova_claw.capabilities.agents.config import AgentConfig
from sensenova_claw.capabilities.mcp.runtime import (
    McpSessionManager,
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
