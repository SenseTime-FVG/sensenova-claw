"""上下文压缩模块单元测试"""

import json
import tempfile
from pathlib import Path

import pytest
from agentos.kernel.runtime.context_compressor import (
    TokenCounter,
    parse_turn_boundaries,
    save_original_messages,
)


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
