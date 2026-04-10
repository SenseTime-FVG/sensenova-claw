from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from sensenova_claw.capabilities.tools.registry import ToolRegistry
from sensenova_claw.kernel.events.bus import PrivateEventBus, PublicEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.router import BusRouter
from sensenova_claw.kernel.events.types import TOOL_CALL_REQUESTED, TOOL_CALL_RESULT
from sensenova_claw.kernel.runtime.state import SessionStateStore
from sensenova_claw.kernel.runtime.tool_runtime import ToolRuntime
from sensenova_claw.kernel.runtime.workers.tool_worker import ToolSessionWorker
from sensenova_claw.platform.config.config import Config


pytestmark = pytest.mark.asyncio


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


async def test_tool_worker_executes_stdio_mcp_tool(tmp_path: Path):
    config_path = tmp_path / "config.yml"
    config_path.write_text("", encoding="utf-8")
    cfg = Config(config_path=config_path)
    server_script = _write_probe_server(tmp_path)
    cfg.set(
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

    import sensenova_claw.capabilities.tools.registry as registry_module
    import sensenova_claw.kernel.runtime.workers.tool_worker as worker_module
    import sensenova_claw.capabilities.mcp.runtime as mcp_runtime_module

    original_registry_config = registry_module.config
    original_worker_config = worker_module.config
    original_mcp_config = mcp_runtime_module.config
    registry_module.config = cfg
    worker_module.config = cfg
    mcp_runtime_module.config = cfg

    public = PublicEventBus()
    private = PrivateEventBus(session_id="s1", public_bus=public)
    runtime = ToolRuntime(
        bus_router=BusRouter(public_bus=public),
        registry=ToolRegistry(),
        state_store=SessionStateStore(),
    )
    worker = ToolSessionWorker(session_id="s1", private_bus=private, runtime=runtime)
    queue: asyncio.Queue[EventEnvelope] = asyncio.Queue()

    async def collector():
        async for event in public.subscribe():
            await queue.put(event)

    collect_task = asyncio.create_task(collector())

    try:
        await runtime.registry.ensure_mcp_session("s1")
        tools = runtime.registry.as_llm_tools(session_id="s1")
        safe_name = next(tool["name"] for tool in tools if tool["name"].startswith("mcp__probe__echo_probe"))

        await worker._handle(
            EventEnvelope(
                type=TOOL_CALL_REQUESTED,
                session_id="s1",
                turn_id="t1",
                source="agent",
                payload={
                    "tool_call_id": "tc_mcp_1",
                    "tool_name": safe_name,
                    "arguments": {"text": "integration"},
                },
            )
        )

        seen_result = None
        for _ in range(4):
            event = await asyncio.wait_for(queue.get(), timeout=5)
            if event.type == TOOL_CALL_RESULT:
                seen_result = event
                break

        assert seen_result is not None
        assert seen_result.payload["success"] is True
        assert seen_result.payload["result"]["content"][0]["text"] == "MCP_ECHO:integration"
    finally:
        collect_task.cancel()
        await runtime.registry.dispose_mcp_session("s1")
        registry_module.config = original_registry_config
        worker_module.config = original_worker_config
        mcp_runtime_module.config = original_mcp_config
