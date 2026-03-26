"""ProactiveExecutor 单元测试。"""

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
    repo.get_session_messages = AsyncMock(return_value=[
        {"role": "user", "content": "上一问：分析市场规模"},
        {"role": "assistant", "content": "这是市场规模分析结果"},
    ])
    repo.get_session_meta = AsyncMock(return_value={"agent_id": "office-main"})

    agent_runtime = MagicMock()
    agent_runtime.spawn_agent_session = AsyncMock()
    agent_runtime.send_user_input = AsyncMock(return_value="turn_rec_123")
    agent_runtime.context_compressor = MagicMock()
    agent_runtime.context_compressor.compress_if_needed = AsyncMock(side_effect=lambda _sid, history, agent_id="default": history)

    executor = ProactiveExecutor(bus=bus, repo=repo, agent_runtime=agent_runtime, memory_manager=None)
    return executor, bus, repo, agent_runtime


@pytest.mark.asyncio
async def test_recommendation_job_uses_hidden_scratch_session():
    """推荐任务应创建 hidden scratch session，而不是向原会话注入 user_input。"""
    executor, bus, repo, agent_runtime = _build_executor()

    trigger_event = EventEnvelope(
        type="agent.step_completed",
        session_id="user-session-1",
        payload={"step_type": "final"},
    )

    job = _make_recommendation_job()

    with patch.object(executor, '_wait_for_completion', new_callable=AsyncMock) as mock_wait:
        mock_wait.return_value = '{"recommendations": [{"id": "1", "title": "test", "prompt": "do test", "category": "action"}]}'
        session_id, result = await executor.execute_job(job, trigger_event)

    agent_runtime.spawn_agent_session.assert_called_once()
    agent_runtime.send_user_input.assert_not_called()
    assert session_id.startswith("proactive_builtin-turn-end-recommendation_")
    assert session_id != "user-session-1"
    assert result is not None


@pytest.mark.asyncio
async def test_recommendation_job_passes_hidden_scratch_meta_and_history_snapshot():
    """scratch session 应带齐 hidden/source/meta，并使用原会话历史快照构造 prompt。"""
    executor, bus, repo, agent_runtime = _build_executor()

    trigger_event = EventEnvelope(
        type="agent.step_completed",
        session_id="sess-abc",
        payload={},
    )

    job = _make_recommendation_job()

    with patch.object(executor, '_wait_for_completion', new_callable=AsyncMock) as mock_wait:
        mock_wait.return_value = "some result"
        await executor.execute_job(job, trigger_event)

    call_kwargs = agent_runtime.spawn_agent_session.call_args.kwargs
    assert call_kwargs["agent_id"] == "proactive-agent"
    assert call_kwargs["parent_session_id"] == "sess-abc"
    assert call_kwargs["meta"]["type"] == "proactive_recommendation_scratch"
    assert call_kwargs["meta"]["visibility"] == "hidden"
    assert call_kwargs["meta"]["source_session_id"] == "sess-abc"
    assert call_kwargs["meta"]["proactive_job_id"] == "builtin-turn-end-recommendation"
    assert "上一问：分析市场规模" in call_kwargs["user_input"]
    assert "这是市场规模分析结果" in call_kwargs["user_input"]
    assert "生成推荐" in call_kwargs["user_input"]


@pytest.mark.asyncio
async def test_recommendation_job_compresses_source_history_when_available():
    """构造 scratch prompt 时应优先复用现有 context compressor。"""
    executor, bus, repo, agent_runtime = _build_executor()
    agent_runtime.context_compressor.compress_if_needed = AsyncMock(return_value=[
        {"role": "user", "content": "压缩后的历史"},
    ])

    trigger_event = EventEnvelope(
        type="agent.step_completed",
        session_id="user-session-2",
        payload={},
    )

    job = _make_recommendation_job()

    with patch.object(executor, '_wait_for_completion', new_callable=AsyncMock) as mock_wait:
        mock_wait.return_value = "ok"
        await executor.execute_job(job, trigger_event)

    agent_runtime.context_compressor.compress_if_needed.assert_called_once_with(
        "user-session-2",
        repo.get_session_messages.return_value,
        agent_id="office-main",
    )
    call_kwargs = agent_runtime.spawn_agent_session.call_args.kwargs
    assert "压缩后的历史" in call_kwargs["user_input"]


@pytest.mark.asyncio
async def test_recommendation_job_timeout_returns_none():
    """scratch session 超时时应返回 (scratch_session_id, None)。"""
    executor, bus, repo, agent_runtime = _build_executor()

    trigger_event = EventEnvelope(
        type="agent.step_completed",
        session_id="user-session-2",
        payload={},
    )

    job = _make_recommendation_job()

    with patch.object(executor, '_wait_for_completion', new_callable=AsyncMock) as mock_wait:
        mock_wait.return_value = None
        session_id, result = await executor.execute_job(job, trigger_event)

    assert session_id.startswith("proactive_builtin-turn-end-recommendation_")
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
async def test_recommendation_job_updates_job_state_on_success():
    """scratch 推荐成功后应更新 job state。"""
    executor, bus, repo, agent_runtime = _build_executor()

    trigger_event = EventEnvelope(
        type="agent.step_completed",
        session_id="user-session-4",
        payload={},
    )

    job = _make_recommendation_job()
    assert job.state.total_runs == 0

    with patch.object(executor, '_wait_for_completion', new_callable=AsyncMock) as mock_wait:
        mock_wait.return_value = "result text"
        await executor.execute_job(job, trigger_event)

    assert job.state.last_status == "ok"
    assert job.state.total_runs == 1
    assert job.state.consecutive_errors == 0


@pytest.mark.asyncio
async def test_recommendation_job_updates_run_with_repository_columns():
    """scratch 推荐成功后，应使用 proactive_runs 表真实存在的字段名。"""
    executor, bus, repo, agent_runtime = _build_executor()

    trigger_event = EventEnvelope(
        type="agent.step_completed",
        session_id="user-session-6",
        payload={},
    )

    job = _make_recommendation_job()

    with patch.object(executor, '_wait_for_completion', new_callable=AsyncMock) as mock_wait:
        mock_wait.return_value = "result text"
        await executor.execute_job(job, trigger_event)

    create_run_payload = repo.create_proactive_run.call_args.args[0]
    assert create_run_payload["session_id"].startswith("proactive_builtin-turn-end-recommendation_")
    repo.update_proactive_run.assert_called()
    updates = repo.update_proactive_run.call_args.args[1]
    assert updates["status"] == "ok"
    assert "completed_at_ms" in updates
    assert "result_summary" in updates
    assert "ended_at_ms" not in updates
    assert "result_text" not in updates


@pytest.mark.asyncio
async def test_recommendation_job_handles_exception():
    """scratch 推荐异常时应返回 (scratch_session_id, None) 并更新失败状态。"""
    executor, bus, repo, agent_runtime = _build_executor()
    agent_runtime.spawn_agent_session = AsyncMock(side_effect=RuntimeError("connection lost"))

    trigger_event = EventEnvelope(
        type="agent.step_completed",
        session_id="user-session-5",
        payload={},
    )

    job = _make_recommendation_job()
    session_id, result = await executor.execute_job(job, trigger_event)

    assert session_id.startswith("proactive_builtin-turn-end-recommendation_")
    assert result is None
    assert job.state.consecutive_errors == 1
