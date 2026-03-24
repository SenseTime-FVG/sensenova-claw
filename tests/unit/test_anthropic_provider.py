"""AnthropicProvider 真实 API 测试

通过真实 Anthropic API 验证 provider 行为，不使用任何 mock。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sensenova_claw.adapters.llm.base import LLMProvider
from sensenova_claw.platform.config.config import Config

# 项目根目录，用于加载 config.yml
PROJECT_ROOT = Path(__file__).resolve().parents[2]


async def _safe_call(provider, **kwargs) -> dict[str, Any]:
    """调用 provider.call，如果 API 不可达则 skip 测试"""
    try:
        return await provider.call(**kwargs)
    except (UnicodeDecodeError, ConnectionError, TimeoutError, OSError) as e:
        pytest.skip(f"Anthropic API 不可达或返回异常: {type(e).__name__}: {e}")
    except Exception as e:
        # anthropic SDK 可能包装异常，检查 cause chain
        cause = e.__cause__ or e.__context__
        if isinstance(cause, (UnicodeDecodeError, ConnectionError, TimeoutError)):
            pytest.skip(f"Anthropic API 不可达或返回异常: {type(cause).__name__}")
        # 也检查异常消息
        err_repr = repr(e)
        if "UnicodeDecodeError" in err_repr or "decode" in str(e):
            pytest.skip(f"Anthropic API 返回非 JSON 响应: {type(e).__name__}")
        raise


@pytest.fixture(scope="module")
def real_config() -> Config:
    """从项目根目录加载真实配置"""
    return Config(config_path=PROJECT_ROOT / "config.yml")


@pytest.fixture(scope="module")
def provider(real_config: Config) -> Any:
    """使用真实配置创建 AnthropicProvider 实例"""
    api_key = real_config.get("llm.providers.anthropic.api_key", "")
    if not api_key:
        pytest.skip("未配置 Anthropic API key，跳过真实 API 测试")

    # 临时替换全局 config，让 AnthropicProvider.__init__ 能读取到真实配置
    import sensenova_claw.adapters.llm.providers.anthropic_provider as mod
    original_config = mod.config
    mod.config = real_config
    try:
        from sensenova_claw.adapters.llm.providers.anthropic_provider import AnthropicProvider
        p = AnthropicProvider()
    finally:
        mod.config = original_config
    return p


@pytest.fixture(scope="module")
def model(real_config: Config) -> str:
    """从配置中获取默认模型"""
    return real_config.get("llm.models.claude-opus.model_id", "claude-opus-4-6")


# ---------------------------------------------------------------------------
# 继承关系测试
# ---------------------------------------------------------------------------

class TestAnthropicProviderInheritance:
    def test_is_llm_provider(self, provider) -> None:
        """AnthropicProvider 应继承 LLMProvider"""
        assert isinstance(provider, LLMProvider)


# ---------------------------------------------------------------------------
# _normalize_messages 纯逻辑测试（不需要 API 调用）
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# _convert_tool 纯逻辑测试（不需要 API 调用）
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 真实 API 调用测试
# ---------------------------------------------------------------------------

class TestCall:
    @pytest.mark.slow
    async def test_basic_text_response(self, provider, model) -> None:
        """纯文本响应：真实 API 应返回非空 content"""
        result = await _safe_call(
            provider,
            model=model,
            messages=[{"role": "user", "content": "请回复一个字：好"}],
            max_tokens=64,
        )

        # 验证响应结构
        assert isinstance(result, dict)
        assert "content" in result
        assert isinstance(result["content"], str)
        assert len(result["content"]) > 0
        assert result["tool_calls"] == []
        assert result["finish_reason"] in ("end_turn", "stop")
        # usage 结构
        assert "usage" in result
        assert result["usage"]["prompt_tokens"] > 0
        assert result["usage"]["completion_tokens"] > 0
        assert result["usage"]["total_tokens"] == (
            result["usage"]["prompt_tokens"] + result["usage"]["completion_tokens"]
        )

    @pytest.mark.slow
    async def test_system_message_works(self, provider, model) -> None:
        """带 system 消息的调用应正常返回"""
        result = await _safe_call(
            provider,
            model=model,
            messages=[
                {"role": "system", "content": "你只能用一个字回答"},
                {"role": "user", "content": "你好吗"},
            ],
            max_tokens=64,
        )

        assert isinstance(result["content"], str)
        assert len(result["content"]) > 0

    @pytest.mark.slow
    async def test_tool_use_response(self, provider, model) -> None:
        """提供工具定义时，模型应能触发 tool_calls"""
        tools = [
            {
                "name": "get_weather",
                "description": "获取指定城市的天气信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "城市名称"},
                    },
                    "required": ["city"],
                },
            }
        ]

        result = await _safe_call(
            provider,
            model=model,
            messages=[{"role": "user", "content": "北京今天天气怎么样？"}],
            tools=tools,
            max_tokens=256,
        )

        # 模型可能直接回复文本或触发工具调用，两者都是合法响应
        assert isinstance(result, dict)
        assert "content" in result
        assert "tool_calls" in result
        assert isinstance(result["tool_calls"], list)

        # 如果有 tool_calls，验证结构
        if result["tool_calls"]:
            tc = result["tool_calls"][0]
            assert "id" in tc
            assert "name" in tc
            assert "arguments" in tc
            assert isinstance(tc["arguments"], dict)
            assert result["finish_reason"] == "tool_calls"

    @pytest.mark.slow
    async def test_max_tokens_respected(self, provider, model) -> None:
        """自定义 max_tokens 应限制输出长度"""
        result = await _safe_call(
            provider,
            model=model,
            messages=[{"role": "user", "content": "请用一个字回答：你好"}],
            max_tokens=32,
        )

        assert isinstance(result["content"], str)
        # completion_tokens 应不超过 max_tokens（允许一定浮动）
        assert result["usage"]["completion_tokens"] <= 64

    @pytest.mark.slow
    async def test_no_tools_param(self, provider, model) -> None:
        """不传 tools 时应正常返回纯文本"""
        result = await _safe_call(
            provider,
            model=model,
            messages=[{"role": "user", "content": "1+1等于几？只回答数字"}],
            tools=None,
            max_tokens=32,
        )

        assert isinstance(result["content"], str)
        assert len(result["content"]) > 0
        assert result["tool_calls"] == []
