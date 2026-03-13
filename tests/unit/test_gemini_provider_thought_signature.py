"""GeminiProvider thought signature 消息清洗单元测试"""
from __future__ import annotations

import json

from agentos.adapters.llm.providers.gemini_provider import GeminiProvider, has_thought_signature


def _make_signed_assistant(tool_call_id: str = "call_123", direct_format: bool = False) -> dict:
    """构造一条带 thought signature 的 assistant 消息

    direct_format=True: Cloudsway 实际格式（reasoning_details 在顶层）
    direct_format=False: 文档格式（嵌套在 provider_specific_fields 下）
    """
    msg: dict = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": tool_call_id,
                "name": "serper_search",
                "arguments": {"query": "北京天气"},
            }
        ],
    }
    if direct_format:
        msg["reasoning_details"] = [
            {"type": "tool", "text": "serper_search", "signature": "sig_abc123"}
        ]
    else:
        msg["provider_specific_fields"] = {
            "reasoning_details": [
                {"type": "tool", "signature": "sig_abc123"}
            ]
        }
    return msg


def _make_tool_result(tool_call_id: str = "call_123") -> dict:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": "serper_search",
        "content": '{"items": [{"title": "北京今日天气"}]}',
    }


# ── has_thought_signature 检测 ──

def test_has_thought_signature_positive_psf_format() -> None:
    msg = _make_signed_assistant(direct_format=False)
    assert has_thought_signature(msg) is True


def test_has_thought_signature_positive_direct_format() -> None:
    msg = _make_signed_assistant(direct_format=True)
    assert has_thought_signature(msg) is True


def test_has_thought_signature_no_psf() -> None:
    msg = {"role": "assistant", "content": "hello"}
    assert has_thought_signature(msg) is False


def test_has_thought_signature_empty_reasoning() -> None:
    msg = {
        "role": "assistant",
        "content": "",
        "provider_specific_fields": {"reasoning_details": []},
    }
    assert has_thought_signature(msg) is False


def test_has_thought_signature_wrong_type() -> None:
    msg = {
        "role": "assistant",
        "content": "",
        "provider_specific_fields": {
            "reasoning_details": [{"type": "text", "signature": "sig_xxx"}]
        },
    }
    assert has_thought_signature(msg) is False


# ── _clean_messages: signed assistant + tool → user ──

def test_clean_messages_converts_tool_to_user_after_signature_psf() -> None:
    """provider_specific_fields 包装格式下的清洗"""
    provider = GeminiProvider()
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "北京天气怎么样？"},
        _make_signed_assistant(direct_format=False),
        _make_tool_result(),
    ]

    cleaned = provider._clean_messages(messages)

    assert cleaned[0] == {"role": "system", "content": "You are helpful."}
    assert cleaned[1] == {"role": "user", "content": "北京天气怎么样？"}

    assistant = cleaned[2]
    assert assistant["role"] == "assistant"
    assert "provider_specific_fields" in assistant

    tool_msg = cleaned[3]
    assert tool_msg["role"] == "user"
    assert tool_msg["tool_call_id"] == "call_123"


def test_clean_messages_converts_tool_to_user_after_signature_direct() -> None:
    """Cloudsway 直接格式（reasoning_details 顶层）下的清洗"""
    provider = GeminiProvider()
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "北京天气怎么样？"},
        _make_signed_assistant(direct_format=True),
        _make_tool_result(),
    ]

    cleaned = provider._clean_messages(messages)

    # assistant 消息保留 reasoning_details
    assistant = cleaned[2]
    assert assistant["role"] == "assistant"
    assert "reasoning_details" in assistant
    assert assistant["reasoning_details"][0]["signature"] == "sig_abc123"
    # tool_calls 应已归一化为 OpenAI function 格式
    tc = assistant["tool_calls"][0]
    assert tc["type"] == "function"
    assert tc["function"]["name"] == "serper_search"

    # tool 消息应被改写为 role=user
    tool_msg = cleaned[3]
    assert tool_msg["role"] == "user"
    assert tool_msg["tool_call_id"] == "call_123"


def test_clean_messages_no_signature_keeps_tool_role() -> None:
    """没有 thought signature 时，tool 消息保持原样"""
    provider = GeminiProvider()
    assistant = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": "call_456", "name": "fetch_url", "arguments": {"url": "https://example.com"}},
        ],
    }
    tool = {
        "role": "tool",
        "tool_call_id": "call_456",
        "name": "fetch_url",
        "content": "page content",
    }
    messages = [
        {"role": "user", "content": "fetch example.com"},
        assistant,
        tool,
    ]

    cleaned = provider._clean_messages(messages)
    assert cleaned[2]["role"] == "tool"
    assert "provider_specific_fields" not in cleaned[1]


# ── 多轮对话场景 ──

def test_clean_messages_multi_turn_mixed() -> None:
    """第一轮有 signature，第二轮无 signature"""
    provider = GeminiProvider()
    messages = [
        {"role": "user", "content": "q1"},
        _make_signed_assistant("call_1"),
        {"role": "tool", "tool_call_id": "call_1", "name": "serper_search", "content": "r1"},
        # 第二轮 LLM 响应，无 signature
        {
            "role": "assistant",
            "content": "根据搜索结果，北京今天晴天。",
            "tool_calls": [],
        },
        {"role": "user", "content": "q2"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "call_2", "name": "fetch_url", "arguments": {"url": "https://weather.com"}},
            ],
        },
        {"role": "tool", "tool_call_id": "call_2", "name": "fetch_url", "content": "page"},
    ]

    cleaned = provider._clean_messages(messages)

    # 第一轮 tool 应为 user
    assert cleaned[2]["role"] == "user"
    # 第二轮 tool 应保持 tool
    assert cleaned[6]["role"] == "tool"


# ── _rebuild_assistant_message 深拷贝隔离 ──

def test_rebuild_does_not_mutate_original_psf() -> None:
    provider = GeminiProvider()
    original = _make_signed_assistant(direct_format=False)
    rebuilt = provider._rebuild_assistant_message(original)

    rebuilt["provider_specific_fields"]["reasoning_details"][0]["signature"] = "modified"
    assert original["provider_specific_fields"]["reasoning_details"][0]["signature"] == "sig_abc123"


def test_rebuild_does_not_mutate_original_direct() -> None:
    provider = GeminiProvider()
    original = _make_signed_assistant(direct_format=True)
    rebuilt = provider._rebuild_assistant_message(original)

    rebuilt["reasoning_details"][0]["signature"] = "modified"
    assert original["reasoning_details"][0]["signature"] == "sig_abc123"
