"""ProactiveExecutor 单元测试 — 注入模式"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.proactive.executor import ProactiveExecutor
from sensenova_claw.kernel.proactive.models import (
    ProactiveJob, EventTrigger, ProactiveTask, DeliveryConfig, SafetyConfig, JobState,
)


def _make_recommendation_job():
    return ProactiveJob(
        id="builtin-turn-end-recommendation",
        name="会话推荐",
        agent_id="proactive-agent",
        trigger=EventTrigger(
            event_type="agent.step_completed",
            exclude_payload={"source": "recommendation"},
        ),
        task=ProactiveTask(prompt="生成推荐"),
        delivery=DeliveryConfig(channels=["web"], recommendation_type="turn_end"),
        safety=SafetyConfig(max_tool_calls=5, max_llm_calls=3, max_duration_ms=30000),
        state=JobState(),
    )


def _make_normal_job():
    """不带 recommendation_type 的普通 proactive job。"""
    return ProactiveJob(
        id="normal-job",
        name="普通任务",
        agent_id="proactive-agent",
        trigger=EventTrigger(event_type="agent.step_completed"),
        task=ProactiveTask(prompt="执行任务"),
        delivery=DeliveryConfig(channels=["web"]),
        safety=SafetyConfig(max_duration_ms=30000),
        state=JobState(),
    )


def _build_executor():
    bus = MagicMock()
    bus.publish = AsyncMock()
    bus.subscribe_queue = MagicMock(return_value=MagicMock())
    bus.unsubscribe_queue = MagicMock()
    repo = MagicMock()
    repo.create_proactive_run = AsyncMock()
    repo.update_proactive_run = AsyncMock()
    repo.update_proactive_job = AsyncMock()

    agent_runtime = MagicMock()
    agent_runtime.spawn_agent_session = AsyncMock()
    agent_runtime.send_user_input = AsyncMock(return_value="turn_rec_123")

    executor = ProactiveExecutor(bus=bus, repo=repo, agent_runtime=agent_runtime, memory_manager=None)
    return executor, bus, repo, agent_runtime


@pytest.mark.asyncio
async def test_inject_mode_calls_send_user_input():
    """当 trigger_event 存在且 job 有 recommendation_type 时，应调用 send_user_input。"""
    executor, bus, repo, agent_runtime = _build_executor()

    trigger_event = EventEnvelope(
        type="agent.step_completed",
        session_id="user-session-1",
        payload={"step_type": "final"},
    )

    job = _make_recommendation_job()

    with patch.object(executor, '_wait_for_completion_by_turn', new_callable=AsyncMock) as mock_wait:
        mock_wait.return_value = '{"recommendations": [{"id": "1", "title": "test", "prompt": "do test", "category": "action"}]}'
        session_id, result = await executor.execute_job(job, trigger_event)

    agent_runtime.send_user_input.assert_called_once()
    agent_runtime.spawn_agent_session.assert_not_called()
    assert session_id == "user-session-1"
    assert result is not None


@pytest.mark.asyncio
async def test_inject_mode_passes_correct_params():
    """注入模式应传递正确的 session_id、prompt 和 meta。"""
    executor, bus, repo, agent_runtime = _build_executor()

    trigger_event = EventEnvelope(
        type="agent.step_completed",
        session_id="sess-abc",
        payload={},
    )

    job = _make_recommendation_job()

    with patch.object(executor, '_wait_for_completion_by_turn', new_callable=AsyncMock) as mock_wait:
        mock_wait.return_value = "some result"
        await executor.execute_job(job, trigger_event)

    call_kwargs = agent_runtime.send_user_input.call_args
    assert call_kwargs.kwargs["session_id"] == "sess-abc"
    assert call_kwargs.kwargs["user_input"] == "生成推荐"
    assert call_kwargs.kwargs["extra_payload"]["meta"]["source"] == "recommendation"


@pytest.mark.asyncio
async def test_inject_mode_timeout_returns_none():
    """注入模式超时时应返回 (session_id, None)。"""
    executor, bus, repo, agent_runtime = _build_executor()

    trigger_event = EventEnvelope(
        type="agent.step_completed",
        session_id="user-session-2",
        payload={},
    )

    job = _make_recommendation_job()

    with patch.object(executor, '_wait_for_completion_by_turn', new_callable=AsyncMock) as mock_wait:
        mock_wait.return_value = None
        session_id, result = await executor.execute_job(job, trigger_event)

    assert session_id == "user-session-2"
    assert result is None
    assert job.state.last_status == "timeout"


@pytest.mark.asyncio
async def test_normal_job_uses_spawn_agent_session():
    """不带 recommendation_type 的 job 应走独立会话模式。"""
    executor, bus, repo, agent_runtime = _build_executor()

    trigger_event = EventEnvelope(
        type="agent.step_completed",
        session_id="user-session-3",
        payload={},
    )

    job = _make_normal_job()

    with patch.object(executor, '_wait_for_completion', new_callable=AsyncMock) as mock_wait:
        mock_wait.return_value = "done"
        session_id, result = await executor.execute_job(job, trigger_event)

    agent_runtime.spawn_agent_session.assert_called_once()
    agent_runtime.send_user_input.assert_not_called()
    assert session_id.startswith("proactive_")


@pytest.mark.asyncio
async def test_inject_mode_updates_job_state_on_success():
    """注入模式成功后应更新 job state。"""
    executor, bus, repo, agent_runtime = _build_executor()

    trigger_event = EventEnvelope(
        type="agent.step_completed",
        session_id="user-session-4",
        payload={},
    )

    job = _make_recommendation_job()
    assert job.state.total_runs == 0

    with patch.object(executor, '_wait_for_completion_by_turn', new_callable=AsyncMock) as mock_wait:
        mock_wait.return_value = "result text"
        await executor.execute_job(job, trigger_event)

    assert job.state.last_status == "ok"
    assert job.state.total_runs == 1
    assert job.state.consecutive_errors == 0


@pytest.mark.asyncio
async def test_inject_mode_handles_exception():
    """注入模式异常时应返回 (session_id, None) 并更新失败状态。"""
    executor, bus, repo, agent_runtime = _build_executor()
    agent_runtime.send_user_input = AsyncMock(side_effect=RuntimeError("connection lost"))

    trigger_event = EventEnvelope(
        type="agent.step_completed",
        session_id="user-session-5",
        payload={},
    )

    job = _make_recommendation_job()
    session_id, result = await executor.execute_job(job, trigger_event)

    assert session_id == "user-session-5"
    assert result is None
    assert job.state.consecutive_errors == 1
