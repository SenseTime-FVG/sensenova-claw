from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from sensenova_claw.capabilities.tools.registry import ToolRegistry
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.router import BusRouter
from sensenova_claw.kernel.events.types import TOOL_CALL_REQUESTED, TOOL_CALL_RESULT
from sensenova_claw.kernel.runtime.tool_runtime import ToolRuntime
from sensenova_claw.platform.config.config import config


def _make_async_client(response: MagicMock) -> tuple[MagicMock, MagicMock]:
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=client)
    manager.__aexit__ = AsyncMock(return_value=None)
    return manager, client


def _make_response(
    *,
    url: str,
    headers: dict[str, str],
    text: str = "",
    content: bytes | None = None,
) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.url = httpx.URL(url)
    response.status_code = 200
    response.headers = headers
    response.text = text
    response.content = content if content is not None else text.encode("utf-8")
    return response


@pytest.mark.asyncio
async def test_fetch_url_tool_runtime_returns_structured_markdown_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("SENSENOVA_CLAW_HOME", str(tmp_path))
    original_config = copy.deepcopy(config.data)
    config.data["tools"]["permission"]["enabled"] = False

    public_bus = PublicEventBus()
    queue = public_bus.subscribe_queue()
    bus_router = BusRouter(public_bus=public_bus)
    tool_runtime = ToolRuntime(bus_router=bus_router, registry=ToolRegistry())
    await tool_runtime.start()

    private_bus = bus_router.get_or_create("fetch-url-session")
    await tool_runtime._create_worker("fetch-url-session", private_bus)
    await asyncio.sleep(0)

    html = """
    <html>
      <body>
        <nav>Home Pricing Docs</nav>
        <article>
          <h1>Release Title</h1>
          <p>Hello <a href="https://example.com/docs">docs</a>.</p>
          <ul><li>Item A</li><li>Item B</li></ul>
        </article>
      </body>
    </html>
    """
    response = _make_response(
        url="https://example.com/release",
        headers={"Content-Type": "text/html; charset=utf-8"},
        text=html,
    )
    manager, _client = _make_async_client(response)

    event = EventEnvelope(
        type=TOOL_CALL_REQUESTED,
        session_id="fetch-url-session",
        turn_id="turn-1",
        source="agent",
        payload={
            "tool_call_id": "tool-fetch-url-1",
            "tool_name": "fetch_url",
            "arguments": {
                "url": "https://example.com/release",
                "format": "markdown",
            },
        },
    )

    try:
        with patch("sensenova_claw.capabilities.tools.builtin.httpx.AsyncClient", return_value=manager):
            await private_bus.publish(event)
            await asyncio.sleep(0.2)

            collected: list[EventEnvelope] = []
            while True:
                try:
                    collected.append(queue.get_nowait())
                except asyncio.QueueEmpty:
                    break

        matched = next(
            (
                current for current in collected
                if current.type == TOOL_CALL_RESULT and current.payload.get("tool_name") == "fetch_url"
            ),
            None,
        )
        assert matched is not None, f"应收到 fetch_url 的 tool.call_result，实际事件: {[evt.type for evt in collected]}"
        result = matched.payload["result"]
        assert matched.payload["success"] is True, matched.payload.get("error")
        assert result["content_type"] == "text/html"
        assert result["format"] == "markdown"
        assert "Release Title" in result["content"]
        assert "[docs](https://example.com/docs)" in result["content"]
        assert "Home Pricing Docs" not in result["content"]
    finally:
        await tool_runtime.stop()
        public_bus.unsubscribe_queue(queue)
        config.data = original_config
