import pytest
from sensenova_claw.kernel.events.envelope import EventEnvelope


def test_extract_meta_source_present():
    from sensenova_claw.kernel.runtime.workers.agent_worker import _extract_meta_source
    payload = {"content": "test", "meta": {"source": "recommendation"}}
    assert _extract_meta_source(payload) == "recommendation"


def test_extract_meta_source_absent():
    from sensenova_claw.kernel.runtime.workers.agent_worker import _extract_meta_source
    payload = {"content": "test"}
    assert _extract_meta_source(payload) is None


def test_extract_meta_source_no_source_key():
    from sensenova_claw.kernel.runtime.workers.agent_worker import _extract_meta_source
    payload = {"content": "test", "meta": {"other": "value"}}
    assert _extract_meta_source(payload) is None


def test_extract_meta_source_meta_not_dict():
    from sensenova_claw.kernel.runtime.workers.agent_worker import _extract_meta_source
    payload = {"content": "test", "meta": "string"}
    assert _extract_meta_source(payload) is None
