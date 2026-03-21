"""上下文压缩集成测试：模拟完整的多轮对话压缩流程"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from agentos.kernel.runtime.context_compressor import ContextCompressor, TokenCounter


def _make_config(max_tokens=500):
    defaults = {
        "context_compression.max_context_tokens": max_tokens,
        "context_compression.phase1_threshold": 0.8,
        "context_compression.phase2_trigger": 0.6,
        "context_compression.phase2_chunk_ratio": 0.3,
        "context_compression.user_input_max_tokens": 50,
        "context_compression.tool_summary_max_tokens": 100,
        "context_compression.phase2_merge_max_tokens": 80,
    }
    mock_config = MagicMock()
    mock_config.get = lambda path, default=None: defaults.get(path, default)
    return mock_config


def _make_factory(summary="摘要"):
    provider = AsyncMock()
    provider.call = AsyncMock(return_value={"content": summary, "tool_calls": []})
    factory = MagicMock()
    factory.get_provider = MagicMock(return_value=provider)
    return factory, provider


class TestEndToEndCompression:
    @pytest.mark.asyncio
    async def test_full_compression_flow(self):
        """模拟 10 轮对话，触发两阶段压缩"""
        factory, provider = _make_factory("简短摘要")
        compressor = ContextCompressor(
            config=_make_config(max_tokens=200),
            llm_factory=factory,
            provider_name="mock", model="mock-v1",
            agentos_home="/tmp/test_integration",
        )

        history = []
        for i in range(10):
            history.append({"role": "user", "content": f"用户问题 {i}: " + "内容" * 50})
            history.append({"role": "assistant", "content": f"助手回答 {i}: " + "回复" * 50})

        result = await compressor.compress_if_needed("integration_sess", history)

        # 应该被压缩（总 token 数减少）
        counter = TokenCounter()
        assert counter.count_messages(result) < counter.count_messages(history)
        # 最后一个 turn 应保留
        assert any("助手回答 9" in (m.get("content") or "") for m in result)
        # LLM 应被调用
        assert provider.call.call_count > 0

    @pytest.mark.asyncio
    async def test_tool_call_turn_compression(self):
        """包含工具调用的 turn 应正确压缩"""
        factory, provider = _make_factory("工具调用摘要")
        compressor = ContextCompressor(
            config=_make_config(max_tokens=200),
            llm_factory=factory,
            provider_name="mock", model="mock-v1",
            agentos_home="/tmp/test_integration2",
        )

        history = [
            {"role": "user", "content": "搜索关于AI的信息 " + "x" * 200},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "tc1", "name": "serper_search", "arguments": {"query": "AI"}}
            ]},
            {"role": "tool", "name": "serper_search", "content": "搜索结果 " + "y" * 200, "tool_call_id": "tc1"},
            {"role": "assistant", "content": "根据搜索结果 " + "z" * 200},
            # 最新 turn
            {"role": "user", "content": "谢谢"},
            {"role": "assistant", "content": "不客气"},
        ]

        result = await compressor.compress_if_needed("tool_sess", history)
        counter = TokenCounter()
        assert counter.count_messages(result) < counter.count_messages(history)

    @pytest.mark.asyncio
    async def test_llm_failure_graceful_degradation(self):
        """LLM 调用失败时应优雅降级"""
        provider = AsyncMock()
        provider.call = AsyncMock(side_effect=Exception("API Error"))
        factory = MagicMock()
        factory.get_provider = MagicMock(return_value=provider)

        compressor = ContextCompressor(
            config=_make_config(max_tokens=100),
            llm_factory=factory,
            provider_name="mock", model="mock-v1",
            agentos_home="/tmp/test_failure",
        )

        history = [
            {"role": "user", "content": "Q " + "x" * 500},
            {"role": "assistant", "content": "A " + "y" * 500},
            {"role": "user", "content": "latest"},
            {"role": "assistant", "content": "answer"},
        ]

        # 不应抛异常
        result = await compressor.compress_if_needed("fail_sess", history)
        assert isinstance(result, list)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_concurrent_compression_safety(self):
        """并发压缩同一 session 应串行化"""
        factory, provider = _make_factory("摘要")
        compressor = ContextCompressor(
            config=_make_config(max_tokens=100),
            llm_factory=factory,
            provider_name="mock", model="mock-v1",
            agentos_home="/tmp/test_concurrent",
        )

        history = [
            {"role": "user", "content": "Q " + "x" * 300},
            {"role": "assistant", "content": "A " + "y" * 300},
            {"role": "user", "content": "latest"},
            {"role": "assistant", "content": "answer"},
        ]

        # 并发调用
        results = await asyncio.gather(
            compressor.compress_if_needed("concurrent_sess", list(history)),
            compressor.compress_if_needed("concurrent_sess", list(history)),
        )
        assert all(isinstance(r, list) for r in results)
