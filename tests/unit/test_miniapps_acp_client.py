from __future__ import annotations

import pytest

from agentos.capabilities.miniapps.acp_client import ACPClient


@pytest.mark.asyncio
async def test_initialize_and_new_session_use_startup_timeout(monkeypatch) -> None:
    client = ACPClient(
        "dummy-acp",
        startup_timeout_seconds=12,
        request_timeout_seconds=180,
    )
    captured: list[tuple[str, float | None]] = []

    async def fake_call(method: str, params: dict, *, timeout_seconds: float | None = None):
        del params
        captured.append((method, timeout_seconds))
        if method == "session/new":
            return {"sessionId": "sess_1"}
        return {}

    monkeypatch.setattr(client, "call", fake_call)

    await client.initialize()
    session_id = await client.new_session("/tmp/workdir")

    assert session_id == "sess_1"
    assert captured == [
        ("initialize", 12),
        ("session/new", 12),
    ]


@pytest.mark.asyncio
async def test_prompt_uses_request_timeout(monkeypatch) -> None:
    client = ACPClient(
        "dummy-acp",
        startup_timeout_seconds=12,
        request_timeout_seconds=240,
    )
    captured: list[tuple[str, float | None, str]] = []

    async def fake_call(method: str, params: dict, *, timeout_seconds: float | None = None):
        captured.append((method, timeout_seconds, str(params.get("sessionId", ""))))
        return {"status": "ok"}

    monkeypatch.setattr(client, "call", fake_call)

    result = await client.prompt("sess_42", "build workspace")

    assert result == {"status": "ok"}
    assert captured == [
        ("session/prompt", 240, "sess_42"),
    ]
