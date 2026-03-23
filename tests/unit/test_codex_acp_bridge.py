from __future__ import annotations

import pytest

from agentos.capabilities.miniapps.codex_acp_bridge import (
    CodexACPBridge,
    build_codex_exec_command,
    _extract_prompt_text,
)


def test_extract_prompt_text_reads_text_items_only() -> None:
    prompt = [
        {"type": "text", "text": "第一段"},
        {"type": "image", "url": "ignored"},
        {"type": "text", "text": "第二段"},
    ]
    assert _extract_prompt_text(prompt) == "第一段\n\n第二段"


def test_build_codex_exec_command_includes_defaults_and_overrides() -> None:
    command = build_codex_exec_command(
        codex_bin="codex",
        cwd="/tmp/workspace",
        prompt="请生成页面",
        output_file="/tmp/out.txt",
        model="gpt-5-codex",
        profile="agentos",
        extra_args=["--dangerously-bypass-approvals-and-sandbox"],
    )

    assert command[:5] == [
        "codex",
        "exec",
        "--skip-git-repo-check",
        "--json",
        "--full-auto",
    ]
    assert "--output-last-message" in command
    assert "--cd" in command
    assert "--model" in command
    assert "--profile" in command
    assert "--dangerously-bypass-approvals-and-sandbox" in command
    assert command[-1] == "请生成页面"


@pytest.mark.asyncio
async def test_bridge_handles_initialize_session_and_prompt() -> None:
    emitted: list[dict] = []

    async def fake_runner(session, prompt_text: str) -> dict:
        assert session.cwd == "/tmp/miniapp"
        assert prompt_text == "请更新页面"
        return {"content": {"text": "done"}, "exitCode": 0}

    bridge = CodexACPBridge(writer=emitted.append, runner=fake_runner)

    await bridge.handle_message({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {},
    })
    assert emitted[-1]["id"] == 1
    assert emitted[-1]["result"]["agentInfo"]["name"] == "Codex ACP Bridge"

    await bridge.handle_message({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "session/new",
        "params": {"cwd": "/tmp/miniapp"},
    })
    session_response = next(item for item in emitted if item.get("id") == 2)
    session_id = session_response["result"]["sessionId"]
    assert session_id.startswith("codex-")

    await bridge.handle_message({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "session/prompt",
        "params": {
            "sessionId": session_id,
            "prompt": [{"type": "text", "text": "请更新页面"}],
        },
    })
    prompt_response = next(item for item in emitted if item.get("id") == 3)
    assert prompt_response["result"] == {"content": {"text": "done"}, "exitCode": 0}
