"""R01: CronJob 模型序列化"""
from app.cron.models import (
    CronJob, CronJobState, CronDelivery,
    AtSchedule, EverySchedule, CronSchedule,
    SystemEventPayload, AgentTurnPayload,
    schedule_to_json, schedule_from_json,
    payload_to_json, payload_from_json,
    cron_job_to_db_row, cron_job_from_db_row,
)


class TestCronModels:
    def test_at_schedule_roundtrip(self):
        s = AtSchedule(at="2026-03-12T10:00:00")
        j = schedule_to_json(s)
        s2 = schedule_from_json(j)
        assert s2.kind == "at"
        assert s2.at == "2026-03-12T10:00:00"

    def test_every_schedule_roundtrip(self):
        s = EverySchedule(every_ms=60000)
        j = schedule_to_json(s)
        s2 = schedule_from_json(j)
        assert s2.kind == "every"
        assert s2.every_ms == 60000

    def test_cron_schedule_roundtrip(self):
        s = CronSchedule(expr="*/5 * * * *")
        j = schedule_to_json(s)
        s2 = schedule_from_json(j)
        assert s2.kind == "cron"
        assert s2.expr == "*/5 * * * *"

    def test_system_event_payload(self):
        p = SystemEventPayload(text="hello")
        j = payload_to_json(p)
        p2 = payload_from_json(j)
        assert p2.kind == "systemEvent"
        assert p2.text == "hello"

    def test_agent_turn_payload(self):
        p = AgentTurnPayload(message="do something")
        j = payload_to_json(p)
        p2 = payload_from_json(j)
        assert p2.kind == "agentTurn"
        assert p2.message == "do something"

    def test_cron_job_db_roundtrip(self):
        job = CronJob(
            id="cron_test1",
            name="Test",
            schedule=EverySchedule(every_ms=60000),
            payload=SystemEventPayload(text="hi"),
            created_at_ms=1000,
            updated_at_ms=1000,
            state=CronJobState(),
        )
        row = cron_job_to_db_row(job)
        assert isinstance(row, dict)
        assert row["id"] == "cron_test1"

        job2 = cron_job_from_db_row(row)
        assert job2.id == "cron_test1"
        assert job2.name == "Test"
