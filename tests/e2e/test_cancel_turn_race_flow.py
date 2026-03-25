from __future__ import annotations

import asyncio
import copy
import uuid
from pathlib import Path

import pytest

from sensenova_claw.adapters.llm.base import LLMProvider
from sensenova_claw.capabilities.tools.base import Tool, ToolRiskLevel
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import (
    AGENT_STEP_COMPLETED,
    ERROR_RAISED,
    LLM_CALL_COMPLETED,
    LLM_CALL_DELTA,
    LLM_CALL_REQUESTED,
    LLM_CALL_RESULT,
    TOOL_CALL_STARTED,
)
from sensenova_claw.platform.config.config import config
from tests.e2e.run_e2e import setup_services, teardown_services


class _RaceProvider(LLMProvider):
    def __init__(self):
        self.calls: list[dict] = []

    async def call(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "race_tool_call_1",
                        "name": "race_blocking_tool",
                        "arguments": {},
                    }
                ],
                "finish_reason": "tool_calls",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        return {
            "content": "第二次 LLM 不应该执行",
            "tool_calls": [],
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }


class _BlockingTool(Tool):
    name = "race_blocking_tool"
    description = "用于取消竞态回归的阻塞工具"
    parameters = {"type": "object", "properties": {}}
    risk_level = ToolRiskLevel.LOW

    def __init__(self):
        self.release = asyncio.Event()
        self.calls = 0

    async def execute(self, **kwargs):
        self.calls += 1
        await self.release.wait()
        return {"success": True, "released": True}


class _StreamingCancelProvider(LLMProvider):
    def __init__(self):
        self.calls: list[dict] = []

    async def call(self, **kwargs):
        raise AssertionError("streaming cancel test should use stream_call")

    async def stream_call(self, **kwargs):
        self.calls.append(kwargs)
        for _ in range(1000):
            await asyncio.sleep(0.05)
            yield {"type": "delta", "content": "abc\n"}
        yield {
            "type": "finish",
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "tool_calls": [],
        }


@pytest.mark.asyncio
async def test_cancel_turn_beats_tool_result_race_and_prevents_second_llm_call(tmp_path: Path):
    original_config = copy.deepcopy(config.data)
    svc = await setup_services(tmp_path, provider="mock", model=None)

    provider = _RaceProvider()
    tool = _BlockingTool()
    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    events: list[EventEnvelope] = []
    tool_started = asyncio.Event()
    finished = asyncio.Event()

    async def collector():
        async for event in svc["bus"].subscribe():
            if event.session_id != session_id:
                continue
            events.append(event)
            if event.type == TOOL_CALL_STARTED:
                tool_started.set()
            if event.type in {ERROR_RAISED, AGENT_STEP_COMPLETED}:
                finished.set()
                break

    collect_task = asyncio.create_task(collector())
    await asyncio.sleep(0.05)

    try:
        svc["llm_runtime"].factory._providers["race"] = provider
        svc["tool_runtime"].registry.register(tool)
        config.data["llm"]["models"]["race-model"] = {
            "provider": "race",
            "model_id": "race-v1",
        }
        config.data["llm"]["default_model"] = "race-model"
        config.data["agent"]["stream"] = False

        await svc["gateway"].send_user_input(session_id, "触发 cancel_turn 竞态")
        await asyncio.wait_for(tool_started.wait(), timeout=5)

        await svc["gateway"].cancel_turn(session_id, reason="user_cancel")
        tool.release.set()

        await asyncio.wait_for(finished.wait(), timeout=5)
        await asyncio.sleep(0.2)
    finally:
        collect_task.cancel()
        await teardown_services(svc)
        config.data = original_config

    event_types = [event.type for event in events]

    assert len(provider.calls) == 1
    assert tool.calls == 1
    assert event_types.count(LLM_CALL_REQUESTED) == 1
    assert TOOL_CALL_STARTED in event_types
    assert AGENT_STEP_COMPLETED not in event_types

    error_event = next(event for event in events if event.type == ERROR_RAISED)
    assert error_event.payload["error_type"] == "TurnCancelled"


@pytest.mark.asyncio
async def test_cancel_turn_stops_inflight_streaming_output(tmp_path: Path):
    original_config = copy.deepcopy(config.data)
    svc = await setup_services(tmp_path, provider="mock", model=None)

    provider = _StreamingCancelProvider()
    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    events: list[EventEnvelope] = []
    first_delta = asyncio.Event()
    cancelled = asyncio.Event()

    async def collector():
        async for event in svc["bus"].subscribe():
            if event.session_id != session_id:
                continue
            events.append(event)
            if event.type == LLM_CALL_DELTA:
                first_delta.set()
            if event.type == ERROR_RAISED and event.payload.get("error_type") == "TurnCancelled":
                cancelled.set()

    collect_task = asyncio.create_task(collector())
    await asyncio.sleep(0.05)

    try:
        svc["llm_runtime"].factory._providers["stream_cancel"] = provider
        config.data["llm"]["models"]["stream-cancel-model"] = {
            "provider": "stream_cancel",
            "model_id": "stream-cancel-v1",
        }
        config.data["llm"]["default_model"] = "stream-cancel-model"
        config.data["agent"]["model"] = "stream-cancel-model"
        config.data["agent"]["stream"] = True

        await svc["gateway"].send_user_input(session_id, "输出 重复abc + 回车 1000次")
        await asyncio.wait_for(first_delta.wait(), timeout=5)

        await svc["gateway"].cancel_turn(session_id, reason="user_cancel")
        await asyncio.wait_for(cancelled.wait(), timeout=5)
        await asyncio.sleep(0.2)
    finally:
        collect_task.cancel()
        await teardown_services(svc)
        config.data = original_config

    event_types = [event.type for event in events]
    delta_events = [event for event in events if event.type == LLM_CALL_DELTA]

    assert provider.calls != []
    assert LLM_CALL_REQUESTED in event_types
    assert len(delta_events) == 1
    assert LLM_CALL_RESULT not in event_types
    assert LLM_CALL_COMPLETED not in event_types
    assert AGENT_STEP_COMPLETED not in event_types

    error_event = next(event for event in events if event.type == ERROR_RAISED)
    assert error_event.payload["error_type"] == "TurnCancelled"
