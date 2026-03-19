from __future__ import annotations

import asyncio
import copy
import uuid
from pathlib import Path
from typing import Any

import pytest

from agentos.platform.config.config import config
from agentos.adapters.llm.base import LLMProvider
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import (
    AGENT_STEP_COMPLETED,
    LLM_CALL_REQUESTED,
    TOOL_CALL_REQUESTED,
    TOOL_CALL_RESULT,
    USER_INPUT,
    USER_QUESTION_ANSWERED,
    USER_QUESTION_ASKED,
)
from tests.e2e.run_e2e import setup_services, teardown_services


class AskUserMockProvider(LLMProvider):
    async def call(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        _ = (model, tools, temperature, max_tokens)
        last = messages[-1] if messages else {"role": "user", "content": ""}

        if last.get("role") == "tool":
            return {
                "content": "收到你的补充信息，继续完成任务。",
                "tool_calls": [],
                "finish_reason": "stop",
                "usage": {"prompt_tokens": 10, "completion_tokens": 12, "total_tokens": 22},
            }

        return {
            "content": "我需要先向你确认关键参数。",
            "tool_calls": [
                {
                    "id": "ask_user_call_1",
                    "name": "ask_user",
                    "arguments": {
                        "question": "请选择部署环境",
                        "options": ["dev", "prod"],
                        "multi_select": False,
                    },
                }
            ],
            "finish_reason": "tool_calls",
            "usage": {"prompt_tokens": 8, "completion_tokens": 10, "total_tokens": 18},
        }


@pytest.mark.asyncio
async def test_ask_user_event_chain_roundtrip(tmp_path: Path) -> None:
    original_config = copy.deepcopy(config.data)
    svc = await setup_services(tmp_path, provider="mock", model="mock-agent-v1")

    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    turn_id = f"turn_{uuid.uuid4().hex[:12]}"
    done = asyncio.Event()
    collected: list[EventEnvelope] = []

    # 强制当前用例走 mock model，避免被本地 config.yml 的真实 provider 覆盖
    config.data["agent"]["model"] = "mock"
    config.data["llm"]["default_model"] = "mock"
    # 注入可控 provider，稳定触发 ask_user 工具调用
    svc["llm_runtime"].factory._providers["mock"] = AskUserMockProvider()

    async def collector() -> None:
        async for event in svc["bus"].subscribe():
            if event.session_id != session_id:
                continue
            collected.append(event)

            if event.type == USER_QUESTION_ASKED:
                await svc["publisher"].publish(
                    EventEnvelope(
                        type=USER_QUESTION_ANSWERED,
                        session_id=session_id,
                        turn_id=turn_id,
                        source="test",
                        payload={
                            "question_id": event.payload.get("question_id"),
                            "answer": "dev",
                            "cancelled": False,
                        },
                    )
                )

            if event.type == AGENT_STEP_COMPLETED:
                done.set()
                break

    task = asyncio.create_task(collector())
    await asyncio.sleep(0.05)

    try:
        await svc["publisher"].publish(
            EventEnvelope(
                type=USER_INPUT,
                session_id=session_id,
                turn_id=turn_id,
                source="test",
                payload={"content": "请先确认环境再回答", "attachments": [], "context_files": []},
            )
        )
        await asyncio.wait_for(done.wait(), timeout=15)
    finally:
        task.cancel()
        await teardown_services(svc)
        config.data = original_config

    event_types = [e.type for e in collected]
    assert USER_QUESTION_ASKED in event_types
    assert USER_QUESTION_ANSWERED in event_types
    assert TOOL_CALL_REQUESTED in event_types
    assert TOOL_CALL_RESULT in event_types
    assert AGENT_STEP_COMPLETED in event_types
    assert event_types.count(LLM_CALL_REQUESTED) >= 2
