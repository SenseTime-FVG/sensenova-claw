"""ProactiveDelivery 单元测试。"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sensenova_claw.kernel.proactive.delivery import ProactiveDelivery
from sensenova_claw.kernel.proactive.models import (
    ProactiveJob, TimeTrigger, ProactiveTask,
    DeliveryConfig, SafetyConfig, JobState,
)


def _make_job(summary_prompt=None):
    return ProactiveJob(
        id="pj-del-1",
        name="投递测试",
        agent_id="proactive-agent",
        trigger=TimeTrigger(cron="* * * * *"),
        task=ProactiveTask(prompt="测试"),
        delivery=DeliveryConfig(channels=["web"], summary_prompt=summary_prompt),
        safety=SafetyConfig(),
        state=JobState(),
    )


@pytest.mark.asyncio
async def test_deliver_retries_on_failure():
    """验证通知发送失败时重试。"""
    bus = MagicMock()
    bus.publish = AsyncMock()
    ns = MagicMock()
    ns.send = AsyncMock(side_effect=[Exception("网络错误"), Exception("网络错误"), None])

    delivery = ProactiveDelivery(bus, ns)
    job = _make_job()

    with patch("sensenova_claw.kernel.proactive.delivery.asyncio.sleep", new_callable=AsyncMock):
        await delivery.deliver(job, "sess-1", "结果")

    assert ns.send.call_count == 3


@pytest.mark.asyncio
async def test_deliver_without_summary_prompt():
    """验证无 summary_prompt 时直接投递原始结果。"""
    bus = MagicMock()
    bus.publish = AsyncMock()
    ns = MagicMock()
    ns.send = AsyncMock()

    delivery = ProactiveDelivery(bus, ns)
    job = _make_job(summary_prompt=None)

    await delivery.deliver(job, "sess-1", "原始结果文本")

    ns.send.assert_called_once()
    notification = ns.send.call_args.args[0]
    assert "原始结果文本" in notification.body


@pytest.mark.asyncio
async def test_deliver_with_summary_prompt():
    """验证有 summary_prompt 时用 LLM 做摘要。"""
    bus = MagicMock()
    bus.publish = AsyncMock()
    ns = MagicMock()
    ns.send = AsyncMock()

    delivery = ProactiveDelivery(bus, ns)
    job = _make_job(summary_prompt="用一句话总结")

    mock_provider = MagicMock()
    mock_provider.call = AsyncMock(return_value={"content": "摘要内容"})
    mock_factory = MagicMock()
    mock_factory.get_provider.return_value = mock_provider

    with patch("sensenova_claw.kernel.proactive.delivery.LLMFactory", return_value=mock_factory):
        await delivery.deliver(job, "sess-1", "很长的原始结果...")

    ns.send.assert_called_once()
    notification = ns.send.call_args.args[0]
    assert "摘要内容" in notification.body


@pytest.mark.asyncio
async def test_deliver_summary_llm_failure_fallback():
    """验证 LLM 摘要失败时回退到原始结果。"""
    bus = MagicMock()
    bus.publish = AsyncMock()
    ns = MagicMock()
    ns.send = AsyncMock()

    delivery = ProactiveDelivery(bus, ns)
    job = _make_job(summary_prompt="用一句话总结")

    mock_provider = MagicMock()
    mock_provider.call = AsyncMock(side_effect=Exception("LLM 调用失败"))
    mock_factory = MagicMock()
    mock_factory.get_provider.return_value = mock_provider

    with patch("sensenova_claw.kernel.proactive.delivery.LLMFactory", return_value=mock_factory):
        await delivery.deliver(job, "sess-1", "原始结果内容")

    ns.send.assert_called_once()
    notification = ns.send.call_args.args[0]
    assert "原始结果内容" in notification.body
