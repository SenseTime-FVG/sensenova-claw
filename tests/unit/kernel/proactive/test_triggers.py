import time
import pytest
from sensenova_claw.kernel.proactive.models import (
    TimeTrigger, EventTrigger, ConditionTrigger, ProactiveJob,
    ProactiveTask, DeliveryConfig, SafetyConfig, JobState,
    parse_duration_ms,
)
from sensenova_claw.kernel.proactive.triggers import (
    compute_next_fire_ms,
    is_event_match,
    should_debounce,
    build_condition_prompt,
    parse_condition_response,
)


def _make_job(trigger, **kwargs) -> ProactiveJob:
    return ProactiveJob(
        id="test", name="test", agent_id="proactive-agent",
        trigger=trigger,
        task=ProactiveTask(prompt="test"),
        delivery=DeliveryConfig(channels=["web"]),
        safety=SafetyConfig(), state=JobState(), **kwargs,
    )


class TestComputeNextFireMs:
    def test_cron_trigger(self):
        trigger = TimeTrigger(cron="0 9 * * *")
        job = _make_job(trigger)
        now_ms = int(time.time() * 1000)
        next_ms = compute_next_fire_ms(job, now_ms)
        assert next_ms is not None
        assert next_ms > now_ms

    def test_every_trigger(self):
        trigger = TimeTrigger(every="30m")
        job = _make_job(trigger)
        now_ms = int(time.time() * 1000)
        next_ms = compute_next_fire_ms(job, now_ms)
        assert next_ms is not None
        assert next_ms == now_ms + parse_duration_ms("30m")

    def test_condition_trigger(self):
        trigger = ConditionTrigger(condition="test", check_interval="10m")
        job = _make_job(trigger)
        now_ms = int(time.time() * 1000)
        next_ms = compute_next_fire_ms(job, now_ms)
        assert next_ms == now_ms + parse_duration_ms("10m")

    def test_event_trigger_returns_none(self):
        trigger = EventTrigger(event_type="email.received")
        job = _make_job(trigger)
        assert compute_next_fire_ms(job, 0) is None


class TestEventMatch:
    def test_type_match(self):
        trigger = EventTrigger(event_type="email.received")
        assert is_event_match(trigger, "email.received", {}) is True
        assert is_event_match(trigger, "email.sent", {}) is False

    def test_filter_match(self):
        trigger = EventTrigger(event_type="email.received", filter={"source": "email-agent"})
        assert is_event_match(trigger, "email.received", {"source": "email-agent"}) is True
        assert is_event_match(trigger, "email.received", {"source": "other"}) is False

    def test_filter_partial_match(self):
        trigger = EventTrigger(event_type="email.received", filter={"source": "email-agent"})
        assert is_event_match(trigger, "email.received", {"source": "email-agent", "extra": 1}) is True


class TestDebounce:
    def test_no_debounce_first_time(self):
        assert should_debounce("job-1", 5000, {}) is False

    def test_debounce_within_window(self):
        now_ms = int(time.time() * 1000)
        last_fires = {"job-1": now_ms - 2000}
        assert should_debounce("job-1", 5000, last_fires) is True

    def test_no_debounce_after_window(self):
        now_ms = int(time.time() * 1000)
        last_fires = {"job-1": now_ms - 6000}
        assert should_debounce("job-1", 5000, last_fires) is False


class TestConditionEvaluation:
    def test_build_prompt(self):
        prompt = build_condition_prompt("有未读邮件", context="最近收到3封邮件")
        assert "有未读邮件" in prompt
        assert "最近收到3封邮件" in prompt
        assert "YES" in prompt

    def test_parse_yes(self):
        assert parse_condition_response("YES") is True
        assert parse_condition_response("yes") is True
        assert parse_condition_response(" YES ") is True

    def test_parse_no(self):
        assert parse_condition_response("NO") is False
        assert parse_condition_response("no") is False

    def test_parse_invalid(self):
        assert parse_condition_response("maybe") is False
        assert parse_condition_response("") is False
