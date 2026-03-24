import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from sensenova_claw.kernel.proactive.delivery import ProactiveDelivery
from sensenova_claw.kernel.proactive.models import DeliveryConfig, ProactiveJob, TimeTrigger, ProactiveTask, SafetyConfig, JobState


def _make_job(channels):
    return ProactiveJob(
        id="j-1", name="测试", agent_id="proactive-agent",
        trigger=TimeTrigger(cron="0 9 * * *"),
        task=ProactiveTask(prompt="test"),
        delivery=DeliveryConfig(channels=channels),
        safety=SafetyConfig(), state=JobState(),
    )


@pytest.fixture
def mock_bus():
    bus = MagicMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mock_notification():
    ns = MagicMock()
    ns.send = AsyncMock()
    return ns


@pytest.mark.asyncio
async def test_deliver_publishes_result_event(mock_bus, mock_notification):
    delivery = ProactiveDelivery(bus=mock_bus, notification_service=mock_notification)
    job = _make_job(["web"])
    await delivery.deliver(job, "session-1", "测试结果")
    mock_bus.publish.assert_called_once()
    event = mock_bus.publish.call_args[0][0]
    assert event.type == "proactive.result"
    assert event.payload["job_name"] == "测试"
    assert event.payload["result"] == "测试结果"


@pytest.mark.asyncio
async def test_deliver_sends_notification(mock_bus, mock_notification):
    delivery = ProactiveDelivery(bus=mock_bus, notification_service=mock_notification)
    job = _make_job(["web", "feishu"])
    await delivery.deliver(job, "session-1", "测试结果")
    mock_notification.send.assert_called_once()
    notification = mock_notification.send.call_args[0][0]
    assert "测试" in notification.title
