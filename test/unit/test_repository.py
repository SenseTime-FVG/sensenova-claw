"""B05: Repository CRUD"""
import pytest

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
