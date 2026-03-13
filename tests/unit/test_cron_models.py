"""Cron 数据模型单元测试"""

import json
import pytest

from agentos.kernel.scheduler.models import (
    AtSchedule,
    CronDelivery,
    CronJob,
    CronJobState,
    CronSchedule,
    EverySchedule,
    SystemEventPayload,
    AgentTurnPayload,
    cron_job_from_db_row,
    cron_job_to_db_row,
    delivery_from_json,
    delivery_to_json,
    payload_from_json,
    payload_to_json,
    schedule_from_json,
    schedule_to_json,
)


# ---------- Schedule 序列化往返 ----------

class TestScheduleSerialization:
    def test_at_schedule_roundtrip(self):
        s = AtSchedule(at="2026-03-15T10:00:00+08:00")
        raw = schedule_to_json(s)
        result = schedule_from_json(raw)
        assert isinstance(result, AtSchedule)
        assert result.at == s.at

    def test_every_schedule_roundtrip(self):
        s = EverySchedule(every_ms=60000, anchor_ms=1000)
        raw = schedule_to_json(s)
        result = schedule_from_json(raw)
        assert isinstance(result, EverySchedule)
        assert result.every_ms == 60000
        assert result.anchor_ms == 1000

    def test_every_schedule_no_anchor(self):
        s = EverySchedule(every_ms=30000)
        raw = schedule_to_json(s)
        result = schedule_from_json(raw)
        assert result.anchor_ms is None

    def test_cron_schedule_roundtrip(self):
        s = CronSchedule(expr="0 9 * * 1-5", tz="Asia/Shanghai")
        raw = schedule_to_json(s)
        result = schedule_from_json(raw)
        assert isinstance(result, CronSchedule)
        assert result.expr == "0 9 * * 1-5"
        assert result.tz == "Asia/Shanghai"

    def test_unknown_kind_raises(self):
        with pytest.raises(ValueError):
            schedule_from_json('{"kind": "unknown"}')


# ---------- Payload 序列化往返 ----------

class TestPayloadSerialization:
    def test_system_event_roundtrip(self):
        p = SystemEventPayload(text="hello")
        raw = payload_to_json(p)
        result = payload_from_json(raw)
        assert isinstance(result, SystemEventPayload)
        assert result.text == "hello"

    def test_agent_turn_roundtrip(self):
        p = AgentTurnPayload(message="do something", model="gpt-4o", timeout_seconds=120, light_context=True)
        raw = payload_to_json(p)
        result = payload_from_json(raw)
        assert isinstance(result, AgentTurnPayload)
        assert result.message == "do something"
        assert result.model == "gpt-4o"
        assert result.timeout_seconds == 120
        assert result.light_context is True

    def test_unknown_kind_raises(self):
        with pytest.raises(ValueError):
            payload_from_json('{"kind": "unknown"}')


# ---------- Delivery 序列化往返 ----------

class TestDeliverySerialization:
    def test_delivery_roundtrip(self):
        d = CronDelivery(mode="announce", channel_id="feishu", to="user123", best_effort=True)
        raw = delivery_to_json(d)
        result = delivery_from_json(raw)
        assert result is not None
        assert result.mode == "announce"
        assert result.channel_id == "feishu"
        assert result.to == "user123"
        assert result.best_effort is True

    def test_delivery_none(self):
        assert delivery_to_json(None) is None
        assert delivery_from_json(None) is None


# ---------- CronJob 序列化往返 ----------

class TestCronJobSerialization:
    def test_roundtrip(self):
        job = CronJob(
            id="cron_test123",
            name="test job",
            schedule=EverySchedule(every_ms=60000),
            session_target="main",
            payload=SystemEventPayload(text="check status"),
            delivery=CronDelivery(mode="announce", channel_id="websocket"),
            enabled=True,
            state=CronJobState(next_run_at_ms=1000000, consecutive_errors=2),
        )
        row = cron_job_to_db_row(job)
        result = cron_job_from_db_row(row)

        assert result.id == "cron_test123"
        assert result.name == "test job"
        assert isinstance(result.schedule, EverySchedule)
        assert result.schedule.every_ms == 60000
        assert result.session_target == "main"
        assert isinstance(result.payload, SystemEventPayload)
        assert result.payload.text == "check status"
        assert result.delivery is not None
        assert result.delivery.channel_id == "websocket"
        assert result.enabled is True
        assert result.state.next_run_at_ms == 1000000
        assert result.state.consecutive_errors == 2

    def test_default_values(self):
        job = CronJob()
        assert job.id.startswith("cron_")
        assert job.enabled is True
        assert job.state.consecutive_errors == 0
        assert job.created_at_ms > 0
