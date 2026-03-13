"""Cron Repository 操作单元测试"""

import time
import pytest
import pytest_asyncio

from agentos.adapters.storage.repository import Repository


@pytest_asyncio.fixture
async def repo(tmp_path):
    """创建临时数据库"""
    db_path = str(tmp_path / "test.db")
    r = Repository(db_path=db_path)
    await r.init()
    return r


class TestCronJobsCRUD:
    async def test_create_and_get(self, repo: Repository):
        job_data = {
            "id": "cron_test001",
            "name": "test job",
            "description": "A test job",
            "schedule_json": '{"kind":"every","every_ms":60000,"anchor_ms":null}',
            "session_target": "main",
            "wake_mode": "now",
            "payload_json": '{"kind":"systemEvent","text":"hello"}',
            "delivery_json": None,
            "enabled": 1,
            "delete_after_run": None,
            "created_at_ms": int(time.time() * 1000),
            "updated_at_ms": int(time.time() * 1000),
            "next_run_at_ms": int(time.time() * 1000) + 60000,
            "running_at_ms": None,
            "last_run_at_ms": None,
            "last_run_status": None,
            "last_error": None,
            "last_duration_ms": None,
            "consecutive_errors": 0,
        }
        await repo.create_cron_job(job_data)
        result = await repo.get_cron_job("cron_test001")
        assert result is not None
        assert result["name"] == "test job"
        assert result["session_target"] == "main"

    async def test_list_jobs(self, repo: Repository):
        for i in range(3):
            await repo.create_cron_job({
                "id": f"cron_{i}",
                "schedule_json": '{"kind":"every","every_ms":1000,"anchor_ms":null}',
                "payload_json": '{"kind":"systemEvent","text":""}',
                "created_at_ms": 1000 + i,
                "updated_at_ms": 1000 + i,
                "enabled": 1 if i < 2 else 0,
                "consecutive_errors": 0,
            })
        all_jobs = await repo.list_cron_jobs()
        assert len(all_jobs) == 3
        enabled_jobs = await repo.list_cron_jobs(enabled_only=True)
        assert len(enabled_jobs) == 2

    async def test_delete_job(self, repo: Repository):
        await repo.create_cron_job({
            "id": "cron_del",
            "schedule_json": '{"kind":"at","at":"2026-01-01"}',
            "payload_json": '{"kind":"systemEvent","text":""}',
            "created_at_ms": 1000,
            "updated_at_ms": 1000,
            "enabled": 1,
            "consecutive_errors": 0,
        })
        await repo.delete_cron_job("cron_del")
        assert await repo.get_cron_job("cron_del") is None

    async def test_get_runnable_jobs(self, repo: Repository):
        now_ms = int(time.time() * 1000)
        # 到期的 job
        await repo.create_cron_job({
            "id": "cron_due",
            "schedule_json": '{"kind":"every","every_ms":1000,"anchor_ms":null}',
            "payload_json": '{"kind":"systemEvent","text":""}',
            "created_at_ms": 1000,
            "updated_at_ms": 1000,
            "enabled": 1,
            "next_run_at_ms": now_ms - 1000,
            "consecutive_errors": 0,
        })
        # 未到期的 job
        await repo.create_cron_job({
            "id": "cron_future",
            "schedule_json": '{"kind":"every","every_ms":1000,"anchor_ms":null}',
            "payload_json": '{"kind":"systemEvent","text":""}',
            "created_at_ms": 1000,
            "updated_at_ms": 1000,
            "enabled": 1,
            "next_run_at_ms": now_ms + 999999,
            "consecutive_errors": 0,
        })
        # 正在运行的 job
        await repo.create_cron_job({
            "id": "cron_running",
            "schedule_json": '{"kind":"every","every_ms":1000,"anchor_ms":null}',
            "payload_json": '{"kind":"systemEvent","text":""}',
            "created_at_ms": 1000,
            "updated_at_ms": 1000,
            "enabled": 1,
            "next_run_at_ms": now_ms - 1000,
            "running_at_ms": now_ms - 500,
            "consecutive_errors": 0,
        })
        runnable = await repo.get_runnable_cron_jobs(now_ms)
        assert len(runnable) == 1
        assert runnable[0]["id"] == "cron_due"

    async def test_clear_stale_running(self, repo: Repository):
        await repo.create_cron_job({
            "id": "cron_stale",
            "schedule_json": '{"kind":"every","every_ms":1000,"anchor_ms":null}',
            "payload_json": '{"kind":"systemEvent","text":""}',
            "created_at_ms": 1000,
            "updated_at_ms": 1000,
            "enabled": 1,
            "running_at_ms": 999,
            "consecutive_errors": 0,
        })
        await repo.clear_stale_cron_running()
        job = await repo.get_cron_job("cron_stale")
        assert job["running_at_ms"] is None


class TestCronRuns:
    async def test_insert_and_update(self, repo: Repository):
        # 先创建关联的 job
        await repo.create_cron_job({
            "id": "cron_runs_test",
            "schedule_json": '{"kind":"every","every_ms":1000,"anchor_ms":null}',
            "payload_json": '{"kind":"systemEvent","text":""}',
            "created_at_ms": 1000,
            "updated_at_ms": 1000,
            "enabled": 1,
            "consecutive_errors": 0,
        })
        run_id = await repo.insert_cron_run({
            "job_id": "cron_runs_test",
            "started_at_ms": 1000,
            "status": "running",
            "created_at": time.time(),
        })
        assert run_id > 0
        await repo.update_cron_run(run_id, {
            "ended_at_ms": 2000,
            "status": "ok",
            "duration_ms": 1000,
        })
