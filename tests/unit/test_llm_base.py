"""LLMProvider 基类单元测试"""
from __future__ import annotations

import pytest

from sensenova_claw.adapters.llm.base import LLMProvider, merge_sampling_extra_body


async def test_call_raises_not_implemented() -> None:
    """基类 call 方法应抛出 NotImplementedError"""
    provider = LLMProvider()
    with pytest.raises(NotImplementedError):
        await provider.call(model="test", messages=[{"role": "user", "content": "hi"}])


async def test_call_with_tools_raises_not_implemented() -> None:
    """带 tools 参数调用基类 call 也应抛出 NotImplementedError"""
    provider = LLMProvider()
    tools = [{"name": "test_tool", "description": "desc", "parameters": {}}]
    with pytest.raises(NotImplementedError):
        await provider.call(
            model="test",
            messages=[{"role": "user", "content": "hi"}],
            tools=tools,
            temperature=0.5,
            max_tokens=100,
        )


def test_base_class_can_be_subclassed() -> None:
    """确认可以正常继承 LLMProvider"""

    class MyProvider(LLMProvider):
        async def call(self, model, messages, tools=None, temperature=0.2, max_tokens=None):
            return {"content": "ok"}

    provider = MyProvider()
    assert isinstance(provider, LLMProvider)


def test_merge_sampling_extra_body_allows_explicit_key_removal() -> None:
    merged = merge_sampling_extra_body({"top_k": None, "reasoning_effort": "medium"})

    assert merged == {"top_p": 0.95, "reasoning_effort": "medium"}
