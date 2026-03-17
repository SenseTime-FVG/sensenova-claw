"""B05: Repository CRUD"""
import pytest

from agentos.kernel.runtime.message_record import MessageRecord

pytestmark = pytest.mark.asyncio


class TestRepository:
    async def test_create_and_list_sessions(self, test_repo):
        await test_repo.create_session("s1", meta={"title": "T1"})
        await test_repo.create_session("s2", meta={"title": "T2"})
        sessions = await test_repo.list_sessions()
        ids = [s["session_id"] for s in sessions]
        assert "s1" in ids and "s2" in ids

    async def test_update_session_activity(self, test_repo):
        await test_repo.create_session("sa")
        await test_repo.update_session_activity("sa")
        sessions = await test_repo.list_sessions()
        s = next(s for s in sessions if s["session_id"] == "sa")
        assert s["last_active"] > 0

    async def test_create_turn_and_complete(self, test_repo):
        await test_repo.create_session("st")
        await test_repo.create_turn("t1", "st", "hello")
        await test_repo.complete_turn("t1", "world")
        turns = await test_repo.get_session_turns("st")
        assert len(turns) >= 1
        assert turns[0]["status"] == "completed"

    async def test_save_and_get_messages(self, test_repo):
        await test_repo.create_session("sm")
        await test_repo.create_turn("tm", "sm", "hi")
        await test_repo.save_message("sm", "tm", "user", content="hello")
        await test_repo.save_message("sm", "tm", "assistant", content="hi there")
        msgs = await test_repo.get_session_messages("sm")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

    async def test_agent_id_column_set_from_meta(self, test_repo):
        """create_session 应同时把 agent_id 写入 meta JSON 和 agent_id 列"""
        await test_repo.create_session("agent_s", meta={"agent_id": "searcher-agent"})
        sessions = await test_repo.list_sessions()
        s = next(s for s in sessions if s["session_id"] == "agent_s")
        assert s["agent_id"] == "searcher-agent"

    async def test_agent_id_column_defaults_to_default(self, test_repo):
        """未指定 agent_id 的 session 列值应为 'default'"""
        await test_repo.create_session("plain_s", meta={"title": "hello"})
        sessions = await test_repo.list_sessions()
        s = next(s for s in sessions if s["session_id"] == "plain_s")
        assert s["agent_id"] == "default"

    async def test_get_session_meta(self, test_repo):
        await test_repo.create_session("meta_s", meta={"agent_id": "helper", "depth": 2})
        meta = await test_repo.get_session_meta("meta_s")
        assert meta["agent_id"] == "helper"
        assert meta["depth"] == 2

    async def test_get_session_meta_nonexist(self, test_repo):
        meta = await test_repo.get_session_meta("nope")
        assert meta is None

    async def test_delete_session_cascade(self, test_repo):
        await test_repo.create_session("del_s")
        await test_repo.create_turn("del_t", "del_s", "x")
        await test_repo.save_message("del_s", "del_t", "user", content="x")
        await test_repo.delete_session_cascade("del_s")
        sessions = await test_repo.list_sessions()
        assert not any(s["session_id"] == "del_s" for s in sessions)

    async def test_cron_crud(self, test_repo):
        import time
        now_ms = int(time.time() * 1000)
        await test_repo.create_cron_job({
            "id": "cj1", "name": "test",
            "schedule_json": '{"cron": "* * * * *"}',
            "payload_json": '{"prompt": "hi"}',
            "created_at_ms": now_ms, "updated_at_ms": now_ms,
            "next_run_at_ms": now_ms,
        })
        job = await test_repo.get_cron_job("cj1")
        assert job is not None
        assert job["name"] == "test"

        await test_repo.update_cron_job("cj1", {"name": "updated"})
        job = await test_repo.get_cron_job("cj1")
        assert job["name"] == "updated"

        await test_repo.delete_cron_job("cj1")
        assert await test_repo.get_cron_job("cj1") is None

    async def test_agent_message_record_crud(self, test_repo):
        record = MessageRecord(
            id="msg_1",
            parent_session_id="parent",
            parent_turn_id="turn_1",
            parent_tool_call_id="tool_1",
            child_session_id="child",
            target_id="helper",
            status="running",
            mode="sync",
            message="请处理",
            result=None,
            error=None,
            depth=1,
            pingpong_count=0,
            created_at=1.0,
            active_turn_id="turn_child_1",
            attempt_count=2,
            max_attempts=3,
            timeout_seconds=12.5,
        )
        await test_repo.save_message_record(record)

        loaded = await test_repo.get_message_record("msg_1")
        assert loaded is not None
        assert loaded.target_id == "helper"
        assert loaded.status == "running"
        assert loaded.active_turn_id == "turn_child_1"
        assert loaded.attempt_count == 2
        assert loaded.max_attempts == 3
        assert loaded.timeout_seconds == 12.5

        record.status = "completed"
        record.result = "done"
        record.completed_at = 2.0
        await test_repo.update_message_record(record)

        by_child = await test_repo.get_message_record_by_child_session("child")
        assert by_child is not None
        assert by_child.result == "done"
        assert by_child.status == "completed"
