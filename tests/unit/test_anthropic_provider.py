"""AnthropicProvider 单元测试

所有 Anthropic SDK 调用均通过 mock 模拟，不发送真实请求。
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentos.adapters.llm.base import LLMProvider


# ---------------------------------------------------------------------------
# 辅助：构造 mock 的 Anthropic API 响应对象
# ---------------------------------------------------------------------------

def _make_text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def _make_tool_use_block(block_id: str, name: str, input_data: dict) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input=input_data)


def _make_usage(input_tokens: int, output_tokens: int) -> SimpleNamespace:
    return SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)


def _make_response(
    content_blocks: list,
    stop_reason: str = "end_turn",
    input_tokens: int = 100,
    output_tokens: int = 50,
) -> SimpleNamespace:
    return SimpleNamespace(
        content=content_blocks,
        stop_reason=stop_reason,
        usage=_make_usage(input_tokens, output_tokens),
    )


# ---------------------------------------------------------------------------
# fixture：创建 AnthropicProvider 实例，mock 掉 config 和 AsyncAnthropic
# ---------------------------------------------------------------------------

@pytest.fixture
def provider():
    """创建一个 mock 了外部依赖的 AnthropicProvider"""
    mock_config = MagicMock()
    mock_config.get.return_value = {"api_key": "sk-test", "timeout": 30}

    with patch("agentos.adapters.llm.providers.anthropic_provider.config", mock_config), \
         patch("agentos.adapters.llm.providers.anthropic_provider.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_client.messages = MagicMock()
        mock_client.messages.create = AsyncMock()
        mock_cls.return_value = mock_client

        from agentos.adapters.llm.providers.anthropic_provider import AnthropicProvider
        p = AnthropicProvider()
        # 将 mock 附到 fixture 上以便测试中设置返回值
        p._mock_create = mock_client.messages.create
        yield p


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------

class TestAnthropicProviderInheritance:
    def test_is_llm_provider(self, provider) -> None:
        """AnthropicProvider 应继承 LLMProvider"""
        assert isinstance(provider, LLMProvider)


class TestCall:
    async def test_basic_text_response(self, provider) -> None:
        """纯文本响应应正确解析"""
        provider._mock_create.return_value = _make_response(
            [_make_text_block("你好！")],
            stop_reason="end_turn",
        )

        result = await provider.call(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "你好"}],
        )

        assert result["content"] == "你好！"
        assert result["tool_calls"] == []
        assert result["finish_reason"] == "end_turn"
        assert result["usage"]["prompt_tokens"] == 100
        assert result["usage"]["completion_tokens"] == 50
        assert result["usage"]["total_tokens"] == 150

    async def test_tool_use_response(self, provider) -> None:
        """带工具调用的响应应正确解析 tool_calls"""
        provider._mock_create.return_value = _make_response(
            [
                _make_text_block("我来搜索一下"),
                _make_tool_use_block("toolu_123", "serper_search", {"q": "test"}),
            ],
        )

        result = await provider.call(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "搜索test"}],
            tools=[{"name": "serper_search", "description": "搜索", "parameters": {"type": "object"}}],
        )

        assert result["content"] == "我来搜索一下"
        assert len(result["tool_calls"]) == 1
        tc = result["tool_calls"][0]
        assert tc["id"] == "toolu_123"
        assert tc["name"] == "serper_search"
        assert tc["arguments"] == {"q": "test"}
        # 有 tool_calls 时 finish_reason 应为 "tool_calls"
        assert result["finish_reason"] == "tool_calls"

    async def test_multiple_tool_calls(self, provider) -> None:
        """多个工具调用应全部解析"""
        provider._mock_create.return_value = _make_response([
            _make_tool_use_block("t1", "tool_a", {"x": 1}),
            _make_tool_use_block("t2", "tool_b", {"y": 2}),
        ])

        result = await provider.call(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "test"}],
            tools=[
                {"name": "tool_a", "description": "a", "parameters": {}},
                {"name": "tool_b", "description": "b", "parameters": {}},
            ],
        )

        assert len(result["tool_calls"]) == 2
        assert result["tool_calls"][0]["name"] == "tool_a"
        assert result["tool_calls"][1]["name"] == "tool_b"
        assert result["content"] == ""

    async def test_system_messages_extracted(self, provider) -> None:
        """system 消息应被提取为 system 参数，不出现在 messages 中"""
        provider._mock_create.return_value = _make_response(
            [_make_text_block("ok")],
        )

        await provider.call(
            model="claude-sonnet-4-20250514",
            messages=[
                {"role": "system", "content": "你是助手"},
                {"role": "system", "content": "请用中文"},
                {"role": "user", "content": "hi"},
            ],
        )

        call_kwargs = provider._mock_create.call_args[1]
        # system 应合并为一个字符串
        assert call_kwargs["system"] == "你是助手\n\n请用中文"
        # messages 中不应包含 system 消息
        for msg in call_kwargs["messages"]:
            assert msg["role"] != "system"

    async def test_no_system_message(self, provider) -> None:
        """无 system 消息时不应传 system 参数"""
        provider._mock_create.return_value = _make_response(
            [_make_text_block("ok")],
        )

        await provider.call(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "hi"}],
        )

        call_kwargs = provider._mock_create.call_args[1]
        assert "system" not in call_kwargs

    async def test_max_tokens_default(self, provider) -> None:
        """未指定 max_tokens 时应默认为 4096"""
        provider._mock_create.return_value = _make_response(
            [_make_text_block("ok")],
        )

        await provider.call(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "hi"}],
        )

        call_kwargs = provider._mock_create.call_args[1]
        assert call_kwargs["max_tokens"] == 4096

    async def test_max_tokens_custom(self, provider) -> None:
        """自定义 max_tokens 应正确传递"""
        provider._mock_create.return_value = _make_response(
            [_make_text_block("ok")],
        )

        await provider.call(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1024,
        )

        call_kwargs = provider._mock_create.call_args[1]
        assert call_kwargs["max_tokens"] == 1024

    async def test_tools_converted_to_anthropic_format(self, provider) -> None:
        """工具定义应转换为 Anthropic 格式（input_schema 替代 parameters）"""
        provider._mock_create.return_value = _make_response(
            [_make_text_block("ok")],
        )

        tools = [
            {
                "name": "my_tool",
                "description": "a useful tool",
                "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
            }
        ]

        await provider.call(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "hi"}],
            tools=tools,
        )

        call_kwargs = provider._mock_create.call_args[1]
        converted = call_kwargs["tools"][0]
        assert converted["name"] == "my_tool"
        assert converted["description"] == "a useful tool"
        assert converted["input_schema"] == tools[0]["parameters"]
        assert "parameters" not in converted

    async def test_no_tools_param_when_tools_none(self, provider) -> None:
        """tools 为 None 时不应传 tools 参数"""
        provider._mock_create.return_value = _make_response(
            [_make_text_block("ok")],
        )

        await provider.call(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
        )

        call_kwargs = provider._mock_create.call_args[1]
        assert "tools" not in call_kwargs


class TestNormalizeMessages:
    def test_user_message_passthrough(self, provider) -> None:
        """user 消息应原样传递"""
        result = provider._normalize_messages([
            {"role": "user", "content": "hello"},
        ])
        assert result == [{"role": "user", "content": "hello"}]

    def test_assistant_with_text_only(self, provider) -> None:
        """仅文本的 assistant 消息应转换为 content 列表"""
        result = provider._normalize_messages([
            {"role": "assistant", "content": "回复"},
        ])
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == [{"type": "text", "text": "回复"}]

    def test_assistant_with_tool_calls(self, provider) -> None:
        """带 tool_calls 的 assistant 消息应转换为 tool_use 格式"""
        result = provider._normalize_messages([
            {
                "role": "assistant",
                "content": "搜索中",
                "tool_calls": [
                    {"id": "call_1", "name": "search", "arguments": {"q": "test"}},
                ],
            },
        ])

        content = result[0]["content"]
        assert len(content) == 2
        assert content[0] == {"type": "text", "text": "搜索中"}
        assert content[1]["type"] == "tool_use"
        assert content[1]["id"] == "call_1"
        assert content[1]["name"] == "search"
        assert content[1]["input"] == {"q": "test"}

    def test_assistant_empty_content_no_tool_calls(self, provider) -> None:
        """assistant 消息 content 为空且无 tool_calls 时 content 列表为空"""
        result = provider._normalize_messages([
            {"role": "assistant", "content": ""},
        ])
        # content 为空字符串视为 falsy，不加 text block
        assert result[0]["content"] == []

    def test_tool_message_to_user_tool_result(self, provider) -> None:
        """tool 消息应转为 user 角色 + tool_result 格式"""
        result = provider._normalize_messages([
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": '{"result": "ok"}',
            },
        ])

        assert result[0]["role"] == "user"
        assert result[0]["content"][0]["type"] == "tool_result"
        assert result[0]["content"][0]["tool_use_id"] == "call_1"
        assert result[0]["content"][0]["content"] == '{"result": "ok"}'

    def test_tool_message_fallback_to_name(self, provider) -> None:
        """tool 消息无 tool_call_id 时应回退到 name 字段"""
        result = provider._normalize_messages([
            {
                "role": "tool",
                "name": "my_tool",
                "content": "result",
            },
        ])

        assert result[0]["content"][0]["tool_use_id"] == "my_tool"


class TestConvertTool:
    def test_convert_tool_format(self, provider) -> None:
        """工具格式转换：parameters -> input_schema"""
        tool = {
            "name": "test_tool",
            "description": "test description",
            "parameters": {"type": "object", "properties": {}},
        }
        converted = provider._convert_tool(tool)
        assert converted["name"] == "test_tool"
        assert converted["description"] == "test description"
        assert converted["input_schema"] == {"type": "object", "properties": {}}

    def test_convert_tool_missing_description(self, provider) -> None:
        """缺少 description 时应默认为空字符串"""
        tool = {"name": "t", "parameters": {}}
        converted = provider._convert_tool(tool)
        assert converted["description"] == ""

    def test_convert_tool_missing_parameters(self, provider) -> None:
        """缺少 parameters 时应默认为空 dict"""
        tool = {"name": "t", "description": "d"}
        converted = provider._convert_tool(tool)
        assert converted["input_schema"] == {}
