"""SessionJsonlWriter 单元测试"""

import json

import pytest

from agentos.adapters.storage.session_jsonl import SessionJsonlWriter


class TestSessionJsonlWriter:
    def test_append_creates_file_and_writes_line(self, tmp_path):
        writer = SessionJsonlWriter(base_dir=tmp_path)
        writer.append("searcher-agent", "sess_abc", "turn_1", {
            "role": "user", "content": "hello",
        })

        path = tmp_path / "searcher-agent" / "sessions" / "sess_abc.jsonl"
        assert path.exists()
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        obj = json.loads(lines[0])
        assert obj["role"] == "user"
        assert obj["content"] == "hello"
        assert obj["session_id"] == "sess_abc"
        assert obj["turn_id"] == "turn_1"
        assert "ts" in obj

    def test_append_multiple_messages(self, tmp_path):
        writer = SessionJsonlWriter(base_dir=tmp_path)
        writer.append("default", "s1", "t1", {"role": "user", "content": "hi"})
        writer.append("default", "s1", "t1", {"role": "assistant", "content": "hello!"})
        writer.append("default", "s1", "t1", {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "tc1", "name": "bash_command", "arguments": "{}"}],
        })
        writer.append("default", "s1", "t1", {
            "role": "tool", "content": "ok", "name": "bash_command", "tool_call_id": "tc1",
        })

        path = tmp_path / "default" / "sessions" / "s1.jsonl"
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 4

        tool_msg = json.loads(lines[3])
        assert tool_msg["role"] == "tool"
        assert tool_msg["name"] == "bash_command"
        assert tool_msg["tool_call_id"] == "tc1"

        assistant_tc = json.loads(lines[2])
        assert len(assistant_tc["tool_calls"]) == 1

    def test_different_agents_separate_dirs(self, tmp_path):
        writer = SessionJsonlWriter(base_dir=tmp_path)
        writer.append("agent-a", "s1", "t1", {"role": "user", "content": "a"})
        writer.append("agent-b", "s2", "t1", {"role": "user", "content": "b"})

        assert (tmp_path / "agent-a" / "sessions" / "s1.jsonl").exists()
        assert (tmp_path / "agent-b" / "sessions" / "s2.jsonl").exists()

    def test_different_sessions_separate_files(self, tmp_path):
        writer = SessionJsonlWriter(base_dir=tmp_path)
        writer.append("default", "s1", "t1", {"role": "user", "content": "a"})
        writer.append("default", "s2", "t1", {"role": "user", "content": "b"})

        assert (tmp_path / "default" / "sessions" / "s1.jsonl").exists()
        assert (tmp_path / "default" / "sessions" / "s2.jsonl").exists()
        lines_s1 = (tmp_path / "default" / "sessions" / "s1.jsonl").read_text(encoding="utf-8").strip().split("\n")
        lines_s2 = (tmp_path / "default" / "sessions" / "s2.jsonl").read_text(encoding="utf-8").strip().split("\n")
        assert len(lines_s1) == 1
        assert len(lines_s2) == 1

    def test_system_role_skipped_by_worker_not_writer(self, tmp_path):
        """Writer 本身不过滤 system（过滤在 _persist_message 层），直接写入即可"""
        writer = SessionJsonlWriter(base_dir=tmp_path)
        writer.append("default", "s1", "t1", {"role": "system", "content": "sys"})
        path = tmp_path / "default" / "sessions" / "s1.jsonl"
        assert path.exists()

    def test_chinese_content(self, tmp_path):
        writer = SessionJsonlWriter(base_dir=tmp_path)
        writer.append("default", "s1", "t1", {"role": "user", "content": "你好世界"})
        path = tmp_path / "default" / "sessions" / "s1.jsonl"
        obj = json.loads(path.read_text(encoding="utf-8").strip())
        assert obj["content"] == "你好世界"

    def test_delete_session_file_removes_existing_jsonl(self, tmp_path):
        writer = SessionJsonlWriter(base_dir=tmp_path)
        writer.append("helper", "sess_to_delete", "t1", {"role": "user", "content": "bye"})

        path = tmp_path / "helper" / "sessions" / "sess_to_delete.jsonl"
        assert path.exists()

        deleted = writer.delete_session_file("helper", "sess_to_delete")

        assert deleted is True
        assert path.exists() is False

    def test_delete_session_file_returns_false_when_missing(self, tmp_path):
        writer = SessionJsonlWriter(base_dir=tmp_path)

        deleted = writer.delete_session_file("helper", "missing")

        assert deleted is False
