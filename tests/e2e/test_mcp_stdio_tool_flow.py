from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

from sensenova_claw.kernel.events.types import (
    AGENT_STEP_COMPLETED,
    LLM_CALL_REQUESTED,
    TOOL_CALL_REQUESTED,
    TOOL_CALL_RESULT,
)
from sensenova_claw.platform.config.config import config
from tests.e2e.run_e2e import EXPECTED_TOOL_CHAIN, check_chain, run_single_turn, setup_services, teardown_services


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


@pytest.mark.asyncio
async def test_agent_mcp_stdio_tool_roundtrip(tmp_path: Path) -> None:
    original_config = copy.deepcopy(config.data)
    server_script = _write_probe_server(tmp_path)
    svc = await setup_services(tmp_path, provider="mock", model=None)
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
    try:
        events, _elapsed = await run_single_turn(
            svc,
            "请使用 MCP echo 工具返回一条消息",
            timeout=10,
        )
    finally:
        await teardown_services(svc)
        config.data = original_config

    failures = check_chain(events, EXPECTED_TOOL_CHAIN, "mcp_stdio")
    assert failures == []

    event_types = [event.type for event in events]
    assert LLM_CALL_REQUESTED in event_types
    assert TOOL_CALL_REQUESTED in event_types
    assert TOOL_CALL_RESULT in event_types
    assert AGENT_STEP_COMPLETED in event_types

    tool_requested = next(event for event in events if event.type == TOOL_CALL_REQUESTED)
    assert tool_requested.payload["tool_name"].startswith("mcp__probe__echo_probe")

    tool_result = next(event for event in events if event.type == TOOL_CALL_RESULT)
    assert "MCP_ECHO:" in tool_result.payload["result"]["content"][0]["text"]

    final_event = next(event for event in events if event.type == AGENT_STEP_COMPLETED)
    assert "MCP_ECHO:" in final_event.payload["result"]["content"]
