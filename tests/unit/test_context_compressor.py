"""上下文压缩模块单元测试"""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sensenova_claw.kernel.runtime.context_compressor import (
    ContextCompressor,
    TokenCounter,
    parse_turn_boundaries,
    save_original_messages,
)
from sensenova_claw.kernel.runtime.state import SessionStateStore


class TestSessionStateStoreReplace:
    def test_replace_history(self):
        store = SessionStateStore()
        store._session_history["sess1"] = [
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "old_answer"},
        ]
        new_history = [
            {"role": "user", "content": "compressed"},
            {"role": "assistant", "content": "compressed_answer"},
        ]
        store.replace_history("sess1", new_history)
        assert store.get_session_history("sess1") == new_history

    def test_replace_history_nonexistent_session(self):
        store = SessionStateStore()
        new_history = [{"role": "user", "content": "new"}]
        store.replace_history("sess_new", new_history)
        assert store.get_session_history("sess_new") == new_history


class TestTokenCounter:
    def setup_method(self):
        self.counter = TokenCounter()

    def test_count_text_empty(self):
        assert self.counter.count_text("") == 0

    def test_count_text_english(self):
        text = "Hello world, this is a test message."
        count = self.counter.count_text(text)
        assert 5 < count < 20

    def test_count_text_chinese(self):
        text = "你好世界，这是一条测试消息。"
        count = self.counter.count_text(text)
        assert count > 0

    def test_count_messages_empty(self):
        assert self.counter.count_messages([]) == 0

    def test_count_messages_single_user(self):
        messages = [{"role": "user", "content": "Hello"}]
        count = self.counter.count_messages(messages)
        assert count > 0

    def test_count_messages_with_tool_calls(self):
        messages = [
            {"role": "assistant", "content": "Let me search.",
             "tool_calls": [{"id": "tc1", "name": "search", "arguments": {"query": "test"}}]},
            {"role": "tool", "name": "search", "content": "Search result here", "tool_call_id": "tc1"},
        ]
        count = self.counter.count_messages(messages)
        assert count > 0

    def test_count_messages_none_content(self):
        messages = [{"role": "assistant", "content": None,
                     "tool_calls": [{"id": "tc1", "name": "fn", "arguments": {}}]}]
        count = self.counter.count_messages(messages)
        assert count > 0


class TestTokenCounterFallback:
    def test_fallback_estimation(self):
        counter = TokenCounter()
        estimate = counter._estimate_tokens("Hello world")
        assert estimate > 0


class TestParseTurnBoundaries:
    def test_empty_history(self):
        assert parse_turn_boundaries([]) == []

    def test_single_turn(self):
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        turns = parse_turn_boundaries(history)
        assert len(turns) == 1
        assert turns[0]["start"] == 0
        assert turns[0]["end"] == 2
        assert len(turns[0]["messages"]) == 2

    def test_multiple_turns(self):
        history = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
            {"role": "assistant", "content": "A2"},
        ]
        turns = parse_turn_boundaries(history)
        assert len(turns) == 2
        assert turns[0]["messages"][0]["content"] == "Q1"
        assert turns[1]["messages"][0]["content"] == "Q2"

    def test_turn_with_tool_calls(self):
        history = [
            {"role": "user", "content": "Search for X"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "tc1", "name": "search", "arguments": {}}]},
            {"role": "tool", "name": "search", "content": "Result", "tool_call_id": "tc1"},
            {"role": "assistant", "content": "Found X"},
        ]
        turns = parse_turn_boundaries(history)
        assert len(turns) == 1
        assert len(turns[0]["messages"]) == 4


class TestSaveOriginalMessages:
    def test_save_phase1(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            messages = [{"role": "user", "content": "Hello"}]
            path = save_original_messages(
                base_dir=tmpdir,
                session_id="sess1",
                phase=1,
                messages=messages,
                original_token_count=100,
                compressed_token_count=50,
                turn_id="turn_abc",
            )
            assert Path(path).exists()
            data = json.loads(Path(path).read_text())
            assert data["phase"] == 1
            assert data["session_id"] == "sess1"
            assert data["turn_id"] == "turn_abc"
            assert len(data["original_messages"]) == 1

    def test_save_phase2(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            messages = [{"role": "user", "content": "Hello"}]
            path = save_original_messages(
                base_dir=tmpdir,
                session_id="sess1",
                phase=2,
                messages=messages,
                original_token_count=200,
                compressed_token_count=80,
                chunk_index=0,
            )
            assert Path(path).exists()
            data = json.loads(Path(path).read_text())
            assert data["phase"] == 2
            assert "chunk0" in Path(path).name

    @pytest.mark.asyncio
    async def test_compress_if_needed_saves_under_agent_session_dir(self, tmp_path):
        """压缩原文应落到 agents/<agent>/sessions/<session_id>/ 下。"""
        cfg = _make_config({
            "context_compression.max_context_tokens": 100,
            "context_compression.phase1_threshold": 0.5,
            "context_compression.user_input_max_tokens": 5,
            "context_compression.tool_summary_max_tokens": 10,
        })
        provider = _make_llm_provider("压缩后的内容")
        factory = _make_llm_factory(provider)
        compressor = ContextCompressor(
            config=cfg,
            llm_factory=factory,
            provider_name="mock",
            model="mock-v1",
            sensenova_claw_home=str(tmp_path),
        )
        history = [
            {"role": "user", "content": "A" * 300},
            {"role": "assistant", "content": "B" * 300},
            {"role": "user", "content": "latest question"},
            {"role": "assistant", "content": "latest answer"},
        ]

        await compressor.compress_if_needed("sess_artifact", history, agent_id="doc-organizer")

        expected_dir = tmp_path / "agents" / "doc-organizer" / "sessions" / "sess_artifact"
        saved_files = list(expected_dir.glob("compression_phase1_*.json"))
        assert saved_files


# ── ContextCompressor 测试辅助 ──────────────────────────────


def _make_config(overrides: dict | None = None) -> MagicMock:
    defaults = {
        "context_compression.max_context_tokens": 1000,
        "context_compression.phase1_threshold": 0.8,
        "context_compression.phase2_trigger": 0.6,
        "context_compression.phase2_chunk_ratio": 0.3,
        "context_compression.user_input_max_tokens": 50,
        "context_compression.tool_summary_max_tokens": 100,
        "context_compression.phase2_merge_max_tokens": 80,
    }
    if overrides:
        defaults.update(overrides)
    mock_config = MagicMock()
    mock_config.get = lambda path, default=None: defaults.get(path, default)
    return mock_config


def _make_llm_provider(summary_text: str = "摘要内容") -> AsyncMock:
    provider = AsyncMock()
    provider.call = AsyncMock(return_value={
        "content": summary_text,
        "tool_calls": [],
    })
    return provider


def _make_llm_factory(provider: AsyncMock) -> MagicMock:
    factory = MagicMock()
    factory.get_provider = MagicMock(return_value=provider)
    return factory


class TestPhase1Compression:
    @pytest.mark.asyncio
    async def test_no_compression_needed(self):
        cfg = _make_config({"context_compression.max_context_tokens": 100000})
        provider = _make_llm_provider()
        factory = _make_llm_factory(provider)
        compressor = ContextCompressor(
            config=cfg, llm_factory=factory,
            provider_name="mock", model="mock-v1",
            sensenova_claw_home="/tmp/test",
        )
        history = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]
        result = await compressor.compress_if_needed("sess1", history)
        assert result == history
        provider.call.assert_not_called()

    @pytest.mark.asyncio
    async def test_phase1_compresses_old_turns(self):
        cfg = _make_config({
            "context_compression.max_context_tokens": 100,
            "context_compression.phase1_threshold": 0.5,
            "context_compression.user_input_max_tokens": 5,
            "context_compression.tool_summary_max_tokens": 10,
        })
        provider = _make_llm_provider("压缩后的内容")
        factory = _make_llm_factory(provider)
        compressor = ContextCompressor(
            config=cfg, llm_factory=factory,
            provider_name="mock", model="mock-v1",
            sensenova_claw_home="/tmp/test",
        )
        history = [
            {"role": "user", "content": "A" * 300},
            {"role": "assistant", "content": "B" * 300},
            {"role": "user", "content": "C" * 300},
            {"role": "assistant", "content": "D" * 300},
            {"role": "user", "content": "latest question"},
            {"role": "assistant", "content": "latest answer"},
        ]
        result = await compressor.compress_if_needed("sess1", history)
        # 压缩后 LLM 被调用，且结果中包含压缩标记
        assert provider.call.call_count > 0
        # 压缩后总 token 数应减少
        counter = TokenCounter()
        original_tokens = counter.count_messages(history)
        compressed_tokens = counter.count_messages(result)
        assert compressed_tokens < original_tokens

    @pytest.mark.asyncio
    async def test_phase1_skips_already_compressed(self):
        cfg = _make_config({
            "context_compression.max_context_tokens": 100,
            "context_compression.phase1_threshold": 0.5,
        })
        provider = _make_llm_provider("摘要")
        factory = _make_llm_factory(provider)
        compressor = ContextCompressor(
            config=cfg, llm_factory=factory,
            provider_name="mock", model="mock-v1",
            sensenova_claw_home="/tmp/test",
        )
        history = [
            {"role": "user", "content": "A" * 300},
            {"role": "assistant", "content": "B" * 300},
            {"role": "user", "content": "latest"},
            {"role": "assistant", "content": "answer"},
        ]
        result1 = await compressor.compress_if_needed("sess1", history)
        call_count_1 = provider.call.call_count
        result2 = await compressor.compress_if_needed("sess1", result1)
        call_count_2 = provider.call.call_count
        assert call_count_2 == call_count_1


class TestPhase2Compression:
    @pytest.mark.asyncio
    async def test_phase2_merges_turns(self):
        cfg = _make_config({
            "context_compression.max_context_tokens": 100,
            "context_compression.phase1_threshold": 0.3,
            "context_compression.phase2_trigger": 0.5,
            "context_compression.phase2_chunk_ratio": 0.3,
            "context_compression.phase2_merge_max_tokens": 20,
        })
        provider = _make_llm_provider("合并摘要")
        factory = _make_llm_factory(provider)
        compressor = ContextCompressor(
            config=cfg, llm_factory=factory,
            provider_name="mock", model="mock-v1",
            sensenova_claw_home="/tmp/test",
        )
        history = []
        for i in range(6):
            history.append({"role": "user", "content": f"问题{i} " + "x" * 200})
            history.append({"role": "assistant", "content": f"回答{i} " + "y" * 200})
        history.append({"role": "user", "content": "最新问题"})
        history.append({"role": "assistant", "content": "最新回答"})

        result = await compressor.compress_if_needed("sess2", history)
        # 压缩后总 token 数应减少
        counter = TokenCounter()
        original_tokens = counter.count_messages(history)
        compressed_tokens = counter.count_messages(result)
        assert compressed_tokens < original_tokens

    @pytest.mark.asyncio
    async def test_phase2_not_triggered_when_under_threshold(self):
        cfg = _make_config({
            "context_compression.max_context_tokens": 100000,
            "context_compression.phase1_threshold": 0.01,
            "context_compression.phase2_trigger": 0.99,
        })
        provider = _make_llm_provider("短摘要")
        factory = _make_llm_factory(provider)
        compressor = ContextCompressor(
            config=cfg, llm_factory=factory,
            provider_name="mock", model="mock-v1",
            sensenova_claw_home="/tmp/test",
        )
        history = [
            {"role": "user", "content": "Q"},
            {"role": "assistant", "content": "A"},
            {"role": "user", "content": "latest"},
            {"role": "assistant", "content": "answer"},
        ]
        result = await compressor.compress_if_needed("sess3", history)
        assert len(result) == len(history)


class TestReSummarizePath:
    @pytest.mark.asyncio
    async def test_re_summarize_when_summary_too_long(self):
        """当 LLM 首次返回的摘要超出 max_tokens 时，应再次调用 LLM 精简摘要。

        通过直接测试 _llm_summarize 方法来精确验证 re-summarize 逻辑：
        首次调用返回超长摘要，第二次调用返回精简后的短摘要。
        """
        cfg = _make_config()
        # 首次调用返回超长文本（>5 tokens），第二次调用返回短文本
        long_summary = "A" * 200
        short_summary = "精简后的短摘要"
        provider = AsyncMock()
        provider.call = AsyncMock(side_effect=[
            {"content": long_summary, "tool_calls": []},   # 首次：过长摘要
            {"content": short_summary, "tool_calls": []},  # 再次：精简后摘要
        ])
        factory = _make_llm_factory(provider)
        compressor = ContextCompressor(
            config=cfg, llm_factory=factory,
            provider_name="mock", model="mock-v1",
            sensenova_claw_home="/tmp/test",
        )
        # max_tokens=5 确保长度 200 的摘要超出限制，触发 re-summarize
        result = await compressor._llm_summarize(
            "{content}", "原始内容", max_tokens=5,
        )
        # LLM 应被调用两次：首次摘要 + 一次精简
        assert provider.call.call_count == 2
        # 最终结果应是精简后的短摘要
        assert result == short_summary


class TestLLMFailureGracefulDegradation:
    @pytest.mark.asyncio
    async def test_llm_failure_returns_truncated_content(self):
        """LLM 调用抛出异常时，压缩器应返回截断内容而不是崩溃。"""
        cfg = _make_config({
            "context_compression.max_context_tokens": 100,
            "context_compression.phase1_threshold": 0.5,
            "context_compression.user_input_max_tokens": 5,
            "context_compression.tool_summary_max_tokens": 10,
        })
        provider = AsyncMock()
        provider.call = AsyncMock(side_effect=RuntimeError("LLM 服务不可用"))
        factory = _make_llm_factory(provider)
        compressor = ContextCompressor(
            config=cfg, llm_factory=factory,
            provider_name="mock", model="mock-v1",
            sensenova_claw_home="/tmp/test",
        )
        history = [
            {"role": "user", "content": "A" * 300},
            {"role": "assistant", "content": "B" * 300},
            {"role": "user", "content": "latest"},
            {"role": "assistant", "content": "answer"},
        ]
        # 不应抛出异常
        result = await compressor.compress_if_needed("sess_fail", history)
        assert result is not None
        assert len(result) > 0
        # 结果中应含有截断标记
        all_content = " ".join(m.get("content") or "" for m in result)
        assert "[截断]" in all_content


class TestLastTurnNeverCompressed:
    @pytest.mark.asyncio
    async def test_last_turn_messages_survive_unchanged(self):
        """第一阶段压缩不应修改最后一个 turn 的消息内容。"""
        cfg = _make_config({
            "context_compression.max_context_tokens": 100,
            "context_compression.phase1_threshold": 0.5,
            "context_compression.user_input_max_tokens": 5,
            "context_compression.tool_summary_max_tokens": 10,
        })
        provider = _make_llm_provider("摘要")
        factory = _make_llm_factory(provider)
        compressor = ContextCompressor(
            config=cfg, llm_factory=factory,
            provider_name="mock", model="mock-v1",
            sensenova_claw_home="/tmp/test",
        )
        last_user_content = "最新的用户问题，绝对不能被压缩"
        last_assistant_content = "最新的助手回答，绝对不能被压缩"
        history = [
            {"role": "user", "content": "A" * 300},
            {"role": "assistant", "content": "B" * 300},
            {"role": "user", "content": last_user_content},
            {"role": "assistant", "content": last_assistant_content},
        ]
        result = await compressor.compress_if_needed("sess_last_turn", history)
        # 最后两条消息的内容应完全保留
        assert result[-2]["content"] == last_user_content
        assert result[-1]["content"] == last_assistant_content


class TestPhase2AfterPhase1:
    @pytest.mark.asyncio
    async def test_phase2_handles_phase1_compressed_turns(self):
        """先执行第一阶段压缩，再验证第二阶段能正确处理已压缩的 turn。"""
        cfg = _make_config({
            "context_compression.max_context_tokens": 100,
            "context_compression.phase1_threshold": 0.3,
            "context_compression.phase2_trigger": 0.5,
            "context_compression.phase2_chunk_ratio": 0.3,
            "context_compression.phase2_merge_max_tokens": 20,
        })
        provider = _make_llm_provider("合并摘要内容")
        factory = _make_llm_factory(provider)
        compressor = ContextCompressor(
            config=cfg, llm_factory=factory,
            provider_name="mock", model="mock-v1",
            sensenova_claw_home="/tmp/test",
        )
        # 构造足够多的 turn，使第一阶段和第二阶段都会触发
        history = []
        for i in range(6):
            history.append({"role": "user", "content": f"问题{i} " + "x" * 200})
            history.append({"role": "assistant", "content": f"回答{i} " + "y" * 200})
        history.append({"role": "user", "content": "最新问题"})
        history.append({"role": "assistant", "content": "最新回答"})

        # 第一次压缩（应触发 Phase 1，可能触发 Phase 2）
        result1 = await compressor.compress_if_needed("sess_p1p2", history)
        call_count_after_phase1 = provider.call.call_count
        assert call_count_after_phase1 > 0

        # 第二次压缩：已压缩的 turn 不会再被 Phase 1 重复处理，
        # 但 Phase 2 可能会再次触发（取决于 token 数）。
        result2 = await compressor.compress_if_needed("sess_p1p2", result1)
        # 两次压缩后 token 数均应小于原始
        counter = TokenCounter()
        original_tokens = counter.count_messages(history)
        compressed_tokens_1 = counter.count_messages(result1)
        compressed_tokens_2 = counter.count_messages(result2)
        assert compressed_tokens_1 < original_tokens
        assert compressed_tokens_2 <= compressed_tokens_1
