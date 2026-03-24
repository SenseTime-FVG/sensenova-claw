"""B01: EventEnvelope 创建/序列化"""
from sensenova_claw.kernel.events.envelope import EventEnvelope


class TestEventEnvelope:
    def test_create_with_defaults(self):
        e = EventEnvelope(type="test", session_id="s1")
        assert e.type == "test"
        assert e.session_id == "s1"
        assert e.agent_id == "default"
        assert e.source == "system"
        assert isinstance(e.event_id, str) and len(e.event_id) > 0
        assert e.ts > 0

    def test_payload_default_empty(self):
        e = EventEnvelope(type="t", session_id="s")
        assert e.payload == {}

    def test_custom_fields(self):
        e = EventEnvelope(
            type="tool.call_requested",
            session_id="s1",
            agent_id="helper",
            turn_id="t1",
            step_id="st1",
            trace_id="tr1",
            source="agent",
            payload={"tool": "bash"},
        )
        assert e.agent_id == "helper"
        assert e.turn_id == "t1"
        assert e.step_id == "st1"
        assert e.trace_id == "tr1"
        assert e.source == "agent"
        assert e.payload == {"tool": "bash"}

    def test_serialization_roundtrip(self):
        e = EventEnvelope(
            type="user.input", session_id="s1",
            payload={"content": "hello"},
        )
        d = e.model_dump()
        e2 = EventEnvelope(**d)
        assert e2.type == e.type
        assert e2.session_id == e.session_id
        assert e2.payload == e.payload
        assert e2.event_id == e.event_id

    def test_unique_event_ids(self):
        e1 = EventEnvelope(type="t", session_id="s")
        e2 = EventEnvelope(type="t", session_id="s")
        assert e1.event_id != e2.event_id
