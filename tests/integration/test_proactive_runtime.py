"""ProactiveRuntime 集成测试。"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from sensenova_claw.kernel.proactive.runtime import ProactiveRuntime
from sensenova_claw.kernel.proactive.models import (
    ProactiveJob,
    TimeTrigger,
    EventTrigger,
    ProactiveTask,
    DeliveryConfig,
    SafetyConfig,
    JobState,
)


def _mock_deps():
    bus = MagicMock()
    bus.publish = AsyncMock()
    bus.subscribe = MagicMock(return_value=AsyncMock())
    bus._subscribers = set()

    repo = MagicMock()
    repo.list_proactive_jobs = AsyncMock(return_value=[])
    repo.get_proactive_job = AsyncMock(return_value=None)
    repo.create_proactive_job = AsyncMock()
    repo.create_proactive_run = AsyncMock()
    repo.update_proactive_run = AsyncMock()
    repo.update_proactive_job = AsyncMock()
    repo.delete_proactive_job = AsyncMock()

    agent_runtime = MagicMock()
    agent_runtime.spawn_agent_session = AsyncMock(return_value="turn-1")

    notification_service = MagicMock()
    notification_service.send = AsyncMock()

    return bus, repo, agent_runtime, notification_service


def _make_job(trigger, **kwargs):
    defaults = dict(
        id="pj-int-1",
        name="集成测试",
        agent_id="proactive-agent",
        trigger=trigger,
        task=ProactiveTask(prompt="测试任务"),
        delivery=DeliveryConfig(channels=["web"]),
        safety=SafetyConfig(max_duration_ms=5000),
        state=JobState(),
    )
    defaults.update(kwargs)
    return ProactiveJob(**defaults)


@pytest.mark.asyncio
async def test_execute_job_success():
    """验证 executor.execute_job 成功执行完整链路。"""
    bus, repo, agent_runtime, notification_service = _mock_deps()
    runtime = ProactiveRuntime(
        bus=bus,
        repo=repo,
        agent_runtime=agent_runtime,
        notification_service=notification_service,
    )
    runtime._enabled = True

    job = _make_job(TimeTrigger(cron="* * * * *"))
    runtime._jobs = {"pj-int-1": job}

    # Mock _wait_for_completion on the executor to return immediately
    async def fake_wait(session_id, timeout_ms):
        return "测试结果"

    runtime._executor._wait_for_completion = fake_wait

    await runtime._executor.execute_job(job)

    # spawn_agent_session was called with correct kwargs
    agent_runtime.spawn_agent_session.assert_called_once()
    call_kwargs = agent_runtime.spawn_agent_session.call_args.kwargs
    assert call_kwargs["agent_id"] == "proactive-agent"
    assert call_kwargs["user_input"] == "测试任务"

    # run record was created
    repo.create_proactive_run.assert_called_once()
    run_row = repo.create_proactive_run.call_args.args[0]
    assert run_row["job_id"] == "pj-int-1"
    assert run_row["status"] == "running"

    # state updated to success
    assert job.state.last_status == "ok"
    assert job.state.total_runs == 1
    assert job.state.consecutive_errors == 0

    # run record updated to ok
    repo.update_proactive_run.assert_called()
    update_kwargs = repo.update_proactive_run.call_args.args[1]
    assert update_kwargs["status"] == "ok"

    # job state persisted
    repo.update_proactive_job.assert_called()


@pytest.mark.asyncio
async def test_execute_job_failure_increments_errors():
    """验证执行失败时 consecutive_errors 递增。"""
    bus, repo, agent_runtime, notification_service = _mock_deps()
    agent_runtime.spawn_agent_session = AsyncMock(side_effect=Exception("模拟错误"))

    runtime = ProactiveRuntime(
        bus=bus,
        repo=repo,
        agent_runtime=agent_runtime,
        notification_service=notification_service,
    )
    runtime._enabled = True

    job = _make_job(TimeTrigger(cron="* * * * *"))
    runtime._jobs = {"pj-int-1": job}

    await runtime._executor.execute_job(job)

    assert job.state.consecutive_errors == 1
    assert job.state.last_status == "error"
    assert job.state.total_runs == 0

    # run record updated to error
    repo.update_proactive_run.assert_called()
    update_kwargs = repo.update_proactive_run.call_args.args[1]
    assert update_kwargs["status"] == "error"


@pytest.mark.asyncio
async def test_auto_disable_after_errors():
    """验证连续失败达到阈值后自动禁用。"""
    bus, repo, agent_runtime, notification_service = _mock_deps()
    agent_runtime.spawn_agent_session = AsyncMock(side_effect=Exception("模拟错误"))

    runtime = ProactiveRuntime(
        bus=bus,
        repo=repo,
        agent_runtime=agent_runtime,
        notification_service=notification_service,
    )
    runtime._enabled = True

    job = _make_job(
        TimeTrigger(cron="* * * * *"),
        safety=SafetyConfig(auto_disable_after_errors=2, max_duration_ms=5000),
    )
    runtime._jobs = {"pj-int-1": job}

    # 第一次失败
    await runtime._executor.execute_job(job)
    assert job.state.consecutive_errors == 1
    assert job.enabled is True

    # 第二次失败 — 应触发自动禁用
    await runtime._executor.execute_job(job)
    assert job.state.consecutive_errors == 2
    assert job.enabled is False

    # DB 中 enabled 被置为 0
    update_calls = repo.update_proactive_job.call_args_list
    disable_call = next(
        (c for c in update_calls if c.args[1].get("enabled") == 0),
        None,
    )
    assert disable_call is not None, "应调用 update_proactive_job 将 enabled 置为 0"


@pytest.mark.asyncio
async def test_evaluate_and_execute_skips_disabled_job():
    """验证 _evaluate_and_execute 对已禁用的 job 直接返回 False。"""
    bus, repo, agent_runtime, notification_service = _mock_deps()
    runtime = ProactiveRuntime(
        bus=bus,
        repo=repo,
        agent_runtime=agent_runtime,
        notification_service=notification_service,
    )
    runtime._enabled = True

    job = _make_job(TimeTrigger(cron="* * * * *"), enabled=False)
    runtime._jobs = {"pj-int-1": job}

    result = await runtime._evaluate_and_execute(job)

    assert result is False
    agent_runtime.spawn_agent_session.assert_not_called()


@pytest.mark.asyncio
async def test_evaluate_and_execute_skips_already_running():
    """验证 _evaluate_and_execute 对正在运行的 job 直接返回 False。"""
    bus, repo, agent_runtime, notification_service = _mock_deps()
    runtime = ProactiveRuntime(
        bus=bus,
        repo=repo,
        agent_runtime=agent_runtime,
        notification_service=notification_service,
    )
    runtime._enabled = True

    job = _make_job(TimeTrigger(cron="* * * * *"))
    runtime._jobs = {"pj-int-1": job}
    runtime._executor._running_jobs.add("pj-int-1")

    result = await runtime._evaluate_and_execute(job)

    assert result is False
    agent_runtime.spawn_agent_session.assert_not_called()


@pytest.mark.asyncio
async def test_add_and_remove_job():
    """验证 add_job / remove_job 正确维护内存索引和 DB。"""
    bus, repo, agent_runtime, notification_service = _mock_deps()
    runtime = ProactiveRuntime(
        bus=bus,
        repo=repo,
        agent_runtime=agent_runtime,
        notification_service=notification_service,
    )
    runtime._enabled = True

    job = _make_job(TimeTrigger(every="5m"))

    added = await runtime.add_job(job)
    assert added.id == "pj-int-1"
    assert "pj-int-1" in runtime._jobs
    repo.create_proactive_job.assert_called_once()

    removed = await runtime.remove_job("pj-int-1")
    assert removed is True
    assert "pj-int-1" not in runtime._jobs
    repo.delete_proactive_job.assert_called_once_with("pj-int-1")

    # 删除不存在的 job 返回 False
    removed_again = await runtime.remove_job("pj-int-1")
    assert removed_again is False
