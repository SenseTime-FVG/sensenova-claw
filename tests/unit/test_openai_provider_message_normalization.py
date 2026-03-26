from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from sensenova_claw.adapters.llm.providers.openai_provider import OpenAIProvider


def test_normalize_messages_adds_function_type_and_tool_call_id() -> None:
    provider = OpenAIProvider()

    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "q"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "name": "serper_search",
                    "arguments": {"q": "英超联赛 2023 冠亚军"},
                }
            ],
        },
        {
            "role": "tool",
            "name": "serper_search",
            "tool_call_id": "call_1",
            "content": "{\"items\": []}",
        },
    ]

    normalized = provider._normalize_messages(messages)

    tool_call = normalized[2]["tool_calls"][0]
    assert tool_call["type"] == "function"
    assert tool_call["function"]["name"] == "serper_search"
    assert json.loads(tool_call["function"]["arguments"]) == {"q": "英超联赛 2023 冠亚军"}
    assert normalized[3]["tool_call_id"] == "call_1"


@pytest.mark.asyncio
async def test_call_does_not_restore_default_sampling_key_marked_as_none() -> None:
    provider = OpenAIProvider(source_type="openai-compatible")
    captured: dict[str, object] = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content="ok", tool_calls=None),
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    provider.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=fake_create)
        )
    )

    await provider.call(
        model="proxy-model",
        messages=[{"role": "user", "content": "hi"}],
        extra_body={"top_k": None, "reasoning_effort": "medium"},
    )

    assert captured["extra_body"] == {"top_p": 0.95, "reasoning_effort": "medium"}
