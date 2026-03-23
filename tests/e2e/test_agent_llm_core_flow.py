from __future__ import annotations

import copy
import sqlite3
from pathlib import Path

import pytest

from sensenova_claw.platform.config.config import config
from sensenova_claw.kernel.events.types import (
    AGENT_STEP_COMPLETED,
    LLM_CALL_REQUESTED,
    TOOL_CALL_REQUESTED,
    TOOL_CALL_RESULT,
)
from tests.e2e.run_e2e import run_single_turn, setup_services, teardown_services
from tests.conftest import load_gemini_config, skip_if_gemini_unavailable


def _provider_model(provider_name: str) -> tuple[str, str | None]:
    """根据 provider 名称返回 (provider, model)。"""
    if provider_name == "mock":
        return "mock", None
    if provider_name == "gemini":
        cfg = load_gemini_config()
        return "gemini", cfg["default_model"] if cfg else None
    return provider_name, None


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_name", ["mock", "gemini"])
async def test_agent_tool_roundtrip_runs_two_llm_calls_and_persists_messages(
    tmp_path: Path, provider_name: str
) -> None:
    """覆盖 agent 核心链路：首轮 LLM -> 工具调用 -> 二轮 LLM -> 最终完成。"""
    skip_if_gemini_unavailable(provider_name)

    original_config = copy.deepcopy(config.data)
    provider, model = _provider_model(provider_name)

    # gemini 超时放长
    timeout = 60 if provider_name == "gemini" else 10

    svc = await setup_services(tmp_path, provider=provider, model=model)

    try:
        events, _elapsed = await run_single_turn(
            svc,
            "帮我搜索英超联赛最近3年的冠亚军分别是什么球队",
            timeout=timeout,
        )
    finally:
        await teardown_services(svc)
        config.data = original_config

    event_types = [event.type for event in events]

    if provider_name == "mock":
        # mock provider 固定返回 tool_calls，验证精确链路
        assert event_types.count(LLM_CALL_REQUESTED) == 2
        assert TOOL_CALL_REQUESTED in event_types
        assert TOOL_CALL_RESULT in event_types
        assert AGENT_STEP_COMPLETED in event_types

        llm_requested_events = [event for event in events if event.type == LLM_CALL_REQUESTED]
        assert len(llm_requested_events[0].payload["messages"]) >= 2

        second_messages = llm_requested_events[1].payload["messages"]
        assistant_messages = [msg for msg in second_messages if msg.get("role") == "assistant"]
        assistant_with_tool_calls = [msg for msg in assistant_messages if msg.get("tool_calls")]
        tool_messages = [msg for msg in second_messages if msg.get("role") == "tool"]
        assert assistant_messages
        assert assistant_with_tool_calls
        assert assistant_with_tool_calls[-1]["tool_calls"][0]["name"] == "serper_search"
        assert tool_messages
        assert tool_messages[-1]["tool_call_id"] == "mock_tool_1"

        completed_event = next(event for event in events if event.type == AGENT_STEP_COMPLETED)
        final_content = completed_event.payload["result"]["content"]
        assert "英超冠亚军信息" in final_content

        conn = sqlite3.connect(svc["db_path"])
        try:
            rows = conn.execute(
                "SELECT role, content, tool_calls, tool_call_id, tool_name FROM messages ORDER BY created_at"
            ).fetchall()
        finally:
            conn.close()

        assert [row[0] for row in rows] == ["user", "assistant", "tool", "assistant"]
        assert rows[1][2] is not None
        assert rows[2][3] == "mock_tool_1"
        assert rows[2][4] == "serper_search"
    else:
        # 真实 provider：只验证事件链路完整性，不验证具体文本
        assert AGENT_STEP_COMPLETED in event_types
        assert LLM_CALL_REQUESTED in event_types

        completed_event = next(event for event in events if event.type == AGENT_STEP_COMPLETED)
        final_content = completed_event.payload.get("result", {}).get("content", "")
        assert len(final_content) > 0, "真实 provider 应返回非空内容"
