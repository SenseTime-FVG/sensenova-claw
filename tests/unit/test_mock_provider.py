"""MockProvider 单元测试"""
from __future__ import annotations

from agentos.adapters.llm.providers.mock_provider import MockProvider
from agentos.adapters.llm.base import LLMProvider


async def test_mock_provider_is_llm_provider() -> None:
    """MockProvider 应继承 LLMProvider"""
    provider = MockProvider()
    assert isinstance(provider, LLMProvider)


async def test_default_echo_reply() -> None:
    """普通消息应返回 mock 回复，内容包含用户输入"""
    provider = MockProvider()
    result = await provider.call(
        model="mock-v1",
        messages=[{"role": "user", "content": "你好"}],
    )

    assert "mock 回复" in result["content"]
    assert "你好" in result["content"]
    assert result["tool_calls"] == []
    assert result["finish_reason"] == "stop"
    assert result["usage"]["total_tokens"] == 20


async def test_empty_messages_returns_echo() -> None:
    """空消息列表时不应崩溃"""
    provider = MockProvider()
    result = await provider.call(model="mock-v1", messages=[])
    assert result["finish_reason"] == "stop"
    assert result["tool_calls"] == []


async def test_premier_league_triggers_tool_call() -> None:
    """包含'英超'和'冠亚军'且有 tools 时应触发工具调用"""
    provider = MockProvider()
    tools = [{"name": "serper_search", "description": "search", "parameters": {}}]
    result = await provider.call(
        model="mock-v1",
        messages=[{"role": "user", "content": "请告诉我英超近三年的冠亚军"}],
        tools=tools,
    )

    assert result["finish_reason"] == "tool_calls"
    assert len(result["tool_calls"]) == 1
    tc = result["tool_calls"][0]
    assert tc["id"] == "mock_tool_1"
    assert tc["name"] == "serper_search"
    assert "英超" in tc["arguments"]["q"]


async def test_premier_league_without_tools_no_tool_call() -> None:
    """包含'英超'和'冠亚军'但没有 tools 时不应触发工具调用"""
    provider = MockProvider()
    result = await provider.call(
        model="mock-v1",
        messages=[{"role": "user", "content": "请告诉我英超近三年的冠亚军"}],
        tools=None,
    )

    assert result["finish_reason"] == "stop"
    assert result["tool_calls"] == []
    assert "mock 回复" in result["content"]


async def test_tool_result_message_returns_summary() -> None:
    """最后一条消息为 tool 角色时应返回整理后的答案"""
    provider = MockProvider()
    messages = [
        {"role": "user", "content": "英超冠亚军"},
        {"role": "assistant", "content": "搜索中..."},
        {"role": "tool", "name": "serper_search", "content": '{"items": []}'},
    ]
    result = await provider.call(model="mock-v1", messages=messages)

    assert result["finish_reason"] == "stop"
    assert result["tool_calls"] == []
    assert "整理" in result["content"]
    assert result["usage"]["total_tokens"] == 50


async def test_usage_fields_present() -> None:
    """返回结果应包含 usage 字段"""
    provider = MockProvider()
    result = await provider.call(
        model="mock-v1",
        messages=[{"role": "user", "content": "test"}],
    )
    usage = result["usage"]
    assert "prompt_tokens" in usage
    assert "completion_tokens" in usage
    assert "total_tokens" in usage
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
