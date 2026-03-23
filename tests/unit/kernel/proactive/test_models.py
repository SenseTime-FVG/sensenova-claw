import json
import pytest
from agentos.kernel.proactive.models import (
    ProactiveJob, TimeTrigger, EventTrigger, ConditionTrigger,
    ProactiveTask, DeliveryConfig, SafetyConfig, JobState,
    trigger_to_json, trigger_from_json, job_to_db_row, job_from_db_row,
    parse_duration_ms,
)


def test_time_trigger_cron():
    t = TimeTrigger(cron="0 9 * * *")
    assert t.kind == "time"
    assert t.cron == "0 9 * * *"
    assert t.every is None


def test_time_trigger_every():
    t = TimeTrigger(every="30m")
    assert t.every == "30m"
    assert t.cron is None


def test_event_trigger():
    t = EventTrigger(event_type="email.received", filter={"source": "email-agent"})
    assert t.kind == "event"
    assert t.debounce_ms == 5000


def test_condition_trigger():
    t = ConditionTrigger(condition="有未读邮件")
    assert t.kind == "condition"
    assert t.check_interval == "5m"


def test_trigger_roundtrip_json():
    triggers = [
        TimeTrigger(cron="0 9 * * *", condition="工作日"),
        EventTrigger(event_type="email.received"),
        ConditionTrigger(condition="有未读邮件"),
    ]
    for t in triggers:
        raw = trigger_to_json(t)
        restored = trigger_from_json(raw)
        assert restored == t


def test_job_db_roundtrip():
    job = ProactiveJob(
        id="test-1",
        name="测试任务",
        agent_id="proactive-agent",
        trigger=TimeTrigger(cron="0 9 * * *"),
        task=ProactiveTask(prompt="测试"),
        delivery=DeliveryConfig(channels=["web"]),
        safety=SafetyConfig(),
        state=JobState(),
    )
    row = job_to_db_row(job)
    assert row["id"] == "test-1"
    assert row["name"] == "测试任务"
    restored = job_from_db_row(row)
    assert restored.id == job.id
    assert restored.trigger == job.trigger


def test_parse_duration_ms():
    assert parse_duration_ms("5m") == 300_000
    assert parse_duration_ms("1h") == 3_600_000
    assert parse_duration_ms("30s") == 30_000
    assert parse_duration_ms("2d") == 172_800_000
    with pytest.raises(ValueError):
        parse_duration_ms("invalid")


# ---------- DB 操作测试 ----------

import asyncio
from agentos.adapters.storage.repository import Repository


@pytest.fixture
async def repo(tmp_path):
    r = Repository(str(tmp_path / "test.db"))
    await r.init()
    return r


@pytest.mark.asyncio
async def test_create_and_get_proactive_job(repo):
    job = ProactiveJob(
        id="pj-1", name="测试", agent_id="proactive-agent",
        trigger=TimeTrigger(cron="0 9 * * *"),
        task=ProactiveTask(prompt="test"),
        delivery=DeliveryConfig(channels=["web"]),
        safety=SafetyConfig(), state=JobState(),
    )
    row = job_to_db_row(job)
    await repo.create_proactive_job(row)
    result = await repo.get_proactive_job("pj-1")
    assert result is not None
    assert result["name"] == "测试"


@pytest.mark.asyncio
async def test_list_enabled_proactive_jobs(repo):
    for i in range(3):
        job = ProactiveJob(
            id=f"pj-{i}", name=f"job-{i}", agent_id="proactive-agent",
            enabled=(i != 1),
            trigger=TimeTrigger(cron="0 9 * * *"),
            task=ProactiveTask(prompt="test"),
            delivery=DeliveryConfig(channels=["web"]),
            safety=SafetyConfig(), state=JobState(),
        )
        await repo.create_proactive_job(job_to_db_row(job))
    jobs = await repo.list_proactive_jobs(enabled_only=True)
    assert len(jobs) == 2


@pytest.mark.asyncio
async def test_create_and_list_proactive_runs(repo):
    await repo.create_proactive_run({
        "id": "pr-1", "job_id": "pj-1", "session_id": "s-1",
        "status": "running", "triggered_by": "time",
        "started_at_ms": 1000, "completed_at_ms": None,
        "result_summary": None, "error_message": None,
    })
    runs = await repo.list_proactive_runs("pj-1")
    assert len(runs) == 1
    assert runs[0]["status"] == "running"
