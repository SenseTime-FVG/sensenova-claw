"""兴趣推送功能集成测试。"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from sensenova_claw.kernel.proactive.runtime import ProactiveRuntime


def _mock_deps():
    bus = MagicMock()
    bus.publish = AsyncMock()
    repo = MagicMock()
    repo.list_proactive_jobs = AsyncMock(return_value=[])
    agent_runtime = MagicMock()
    agent_runtime.spawn_agent_session = AsyncMock(return_value="turn-1")
    notification_service = MagicMock()
    notification_service.send = AsyncMock()
    return bus, repo, agent_runtime, notification_service


@pytest.mark.asyncio
async def test_builtin_interest_push_registered():
    """验证内置兴趣推送 job 已注册。"""
    bus, repo, agent_runtime, notification_service = _mock_deps()
    runtime = ProactiveRuntime(bus, repo, agent_runtime, notification_service)

    await runtime.start()

    jobs = await runtime.list_jobs()
    job_ids = [j.id for j in jobs]
    assert "builtin-interest-push" in job_ids


@pytest.mark.asyncio
async def test_trigger_interest_push():
    """验证手动触发兴趣推送。"""
    bus, repo, agent_runtime, notification_service = _mock_deps()
    runtime = ProactiveRuntime(bus, repo, agent_runtime, notification_service)

    await runtime.start()
    await runtime.trigger_job("builtin-interest-push", session_id=None)

    agent_runtime.spawn_agent_session.assert_called_once()


@pytest.mark.asyncio
async def test_concurrent_trigger_rejected():
    """验证并发触发被拒绝。"""
    bus, repo, agent_runtime, notification_service = _mock_deps()
    runtime = ProactiveRuntime(bus, repo, agent_runtime, notification_service)

    await runtime.start()

    runtime._executor._running_jobs.add("builtin-interest-push")

    with pytest.raises(ValueError, match="already running"):
        await runtime.trigger_job("builtin-interest-push", session_id=None)
