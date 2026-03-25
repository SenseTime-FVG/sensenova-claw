"""ProactiveJob 模型单元测试。"""
import json
import pytest
from agentos.kernel.proactive.models import (
    TimeTrigger,
    EventTrigger,
    ProactiveTask,
    DeliveryConfig,
    SafetyConfig,
    JobState,
    ProactiveJob,
    trigger_to_json,
    trigger_from_json,
    job_to_db_row,
    job_from_db_row,
    parse_duration_ms,
)


def test_parse_duration_ms():
    assert parse_duration_ms("5m") == 300_000
    assert parse_duration_ms("1h") == 3_600_000
    assert parse_duration_ms("30s") == 30_000
    assert parse_duration_ms("2d") == 172_800_000


def test_time_trigger_serialization_roundtrip():
    trigger = TimeTrigger(cron="0 9 * * *")
    json_str = trigger_to_json(trigger)
    restored = trigger_from_json(json_str)
    assert isinstance(restored, TimeTrigger)
    assert restored.cron == "0 9 * * *"
    assert restored.every is None


def test_time_trigger_every_serialization():
    trigger = TimeTrigger(every="5m")
    json_str = trigger_to_json(trigger)
    restored = trigger_from_json(json_str)
    assert isinstance(restored, TimeTrigger)
    assert restored.every == "5m"


def test_event_trigger_serialization_roundtrip():
    trigger = EventTrigger(event_type="user.input", filter={"key": "val"}, debounce_ms=3000)
    json_str = trigger_to_json(trigger)
    restored = trigger_from_json(json_str)
    assert isinstance(restored, EventTrigger)
    assert restored.event_type == "user.input"
    assert restored.filter == {"key": "val"}
    assert restored.debounce_ms == 3000


def test_trigger_from_json_unknown_kind_raises():
    with pytest.raises(ValueError, match="Unknown trigger kind"):
        trigger_from_json(json.dumps({"kind": "unknown"}))


def test_job_db_roundtrip():
    job = ProactiveJob(
        id="pj-test",
        name="测试",
        trigger=TimeTrigger(cron="0 2 * * *"),
        task=ProactiveTask(prompt="测试 prompt", use_memory=True),
        delivery=DeliveryConfig(channels=["web"]),
        safety=SafetyConfig(max_llm_calls=5, max_duration_ms=600000),
        state=JobState(),
    )
    row = job_to_db_row(job)
    restored = job_from_db_row(row)
    assert restored.id == "pj-test"
    assert restored.name == "测试"
    assert isinstance(restored.trigger, TimeTrigger)
    assert restored.trigger.cron == "0 2 * * *"
    assert restored.task.use_memory is True
    assert restored.safety.max_llm_calls == 5
