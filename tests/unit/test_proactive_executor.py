"""ProactiveExecutor 单元测试。"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from sensenova_claw.kernel.proactive.models import (
    ProactiveJob, TimeTrigger, ProactiveTask,
    DeliveryConfig, SafetyConfig, JobState,
)


def _make_job(**kwargs):
    defaults = dict(
        id="pj-exec-1",
        name="执行测试",
        agent_id="proactive-agent",
        trigger=TimeTrigger(cron="* * * * *"),
        task=ProactiveTask(prompt="测试任务"),
        delivery=DeliveryConfig(channels=["web"]),
        safety=SafetyConfig(max_duration_ms=5000),
        state=JobState(),
    )
    defaults.update(kwargs)
    return ProactiveJob(**defaults)


@pytest.mark.asyncio
async def test_execute_job_skips_if_already_running():
    """验证并发锁：同一 job 不会重复执行。"""
    from sensenova_claw.kernel.proactive.executor import ProactiveExecutor

    bus = MagicMock()
    bus.publish = AsyncMock()
    bus._subscribers = set()
    bus.subscribe_queue = MagicMock(return_value=asyncio.Queue())
    bus.unsubscribe_queue = MagicMock()
    repo = MagicMock()
    repo.create_proactive_run = AsyncMock()
    repo.update_proactive_run = AsyncMock()
    repo.update_proactive_job = AsyncMock()
    agent_runtime = MagicMock()
    agent_runtime.spawn_agent_session = AsyncMock()

    executor = ProactiveExecutor(
        bus=bus, repo=repo, agent_runtime=agent_runtime,
        memory_manager=None,
    )

    job = _make_job()
    executor._running_jobs.add("pj-exec-1")

    await executor.execute_job(job)

    agent_runtime.spawn_agent_session.assert_not_called()


@pytest.mark.asyncio
async def test_execute_job_handles_timeout():
    """验证 _wait_for_completion 超时时走失败路径。"""
    from sensenova_claw.kernel.proactive.executor import ProactiveExecutor

    bus = MagicMock()
    bus.publish = AsyncMock()
    bus._subscribers = set()
    bus.subscribe_queue = MagicMock(return_value=asyncio.Queue())
    bus.unsubscribe_queue = MagicMock()
    repo = MagicMock()
    repo.create_proactive_run = AsyncMock()
    repo.update_proactive_run = AsyncMock()
    repo.update_proactive_job = AsyncMock()
    agent_runtime = MagicMock()
    agent_runtime.spawn_agent_session = AsyncMock(return_value="turn-1")

    executor = ProactiveExecutor(
        bus=bus, repo=repo, agent_runtime=agent_runtime,
        memory_manager=None,
    )

    job = _make_job(safety=SafetyConfig(max_duration_ms=100))

    await executor.execute_job(job)

    assert job.state.last_status in ("error", "timeout")
    assert job.state.consecutive_errors >= 1


@pytest.mark.asyncio
async def test_lock_cleanup_on_remove():
    """验证 job 删除时清理 lock。"""
    from sensenova_claw.kernel.proactive.executor import ProactiveExecutor

    executor = ProactiveExecutor.__new__(ProactiveExecutor)
    executor._job_locks = {"pj-1": asyncio.Lock()}
    executor._running_jobs = set()

    executor.cleanup_job("pj-1")

    assert "pj-1" not in executor._job_locks


@pytest.mark.asyncio
async def test_execute_job_success_path():
    """验证成功路径：状态更新正确，consecutive_errors 清零。"""
    from sensenova_claw.kernel.proactive.executor import ProactiveExecutor
    from sensenova_claw.kernel.events.envelope import EventEnvelope
    from sensenova_claw.kernel.events.types import AGENT_STEP_COMPLETED

    bus = MagicMock()
    bus.publish = AsyncMock()
    subscribers: set = set()
    bus._subscribers = subscribers
    def _subscribe_queue():
        queue = asyncio.Queue()
        subscribers.add(queue)
        return queue
    def _unsubscribe_queue(queue):
        subscribers.discard(queue)
    bus.subscribe_queue = MagicMock(side_effect=_subscribe_queue)
    bus.unsubscribe_queue = MagicMock(side_effect=_unsubscribe_queue)
    repo = MagicMock()
    repo.create_proactive_run = AsyncMock()
    repo.update_proactive_run = AsyncMock()
    repo.update_proactive_job = AsyncMock()
    agent_runtime = MagicMock()

    async def fake_spawn(agent_id, session_id, user_input, meta):
        # 延迟推送，确保 _wait_for_completion 已订阅
        async def _push():
            await asyncio.sleep(0.1)
            event = EventEnvelope(
                type=AGENT_STEP_COMPLETED,
                session_id=session_id,
                agent_id=agent_id,
                source="agent",
                payload={"result": {"content": "任务完成"}},
            )
            for q in list(subscribers):
                await q.put(event)
        asyncio.create_task(_push())

    agent_runtime.spawn_agent_session = AsyncMock(side_effect=fake_spawn)

    executor = ProactiveExecutor(
        bus=bus, repo=repo, agent_runtime=agent_runtime,
        memory_manager=None,
    )

    job = _make_job(safety=SafetyConfig(max_duration_ms=5000))
    job.state.consecutive_errors = 2  # 预设有错误，成功后应清零

    await executor.execute_job(job)

    assert job.state.last_status == "ok"
    assert job.state.consecutive_errors == 0
    assert job.state.total_runs == 1


@pytest.mark.asyncio
async def test_handle_failure_auto_disables_after_threshold():
    """验证连续失败超过阈值后自动禁用 job。"""
    from sensenova_claw.kernel.proactive.executor import ProactiveExecutor

    bus = MagicMock()
    bus.publish = AsyncMock()
    bus._subscribers = set()
    bus.subscribe_queue = MagicMock(return_value=asyncio.Queue())
    bus.unsubscribe_queue = MagicMock()
    repo = MagicMock()
    repo.create_proactive_run = AsyncMock()
    repo.update_proactive_run = AsyncMock()
    repo.update_proactive_job = AsyncMock()
    agent_runtime = MagicMock()
    agent_runtime.spawn_agent_session = AsyncMock(side_effect=RuntimeError("模拟失败"))

    executor = ProactiveExecutor(
        bus=bus, repo=repo, agent_runtime=agent_runtime,
        memory_manager=None,
    )

    # auto_disable_after_errors=1，第一次失败即禁用
    job = _make_job(safety=SafetyConfig(max_duration_ms=5000, auto_disable_after_errors=1))

    await executor.execute_job(job)

    assert job.enabled is False
    assert job.state.consecutive_errors >= 1


@pytest.mark.asyncio
async def test_build_prompt_with_memory():
    """验证 _build_prompt 在 use_memory=True 时拼接记忆上下文。"""
    from sensenova_claw.kernel.proactive.executor import ProactiveExecutor

    memory_manager = MagicMock()
    memory_manager.get_context = MagicMock(return_value="历史记忆内容")

    executor = ProactiveExecutor.__new__(ProactiveExecutor)
    executor._memory_manager = memory_manager

    job = _make_job(task=ProactiveTask(prompt="基础任务", use_memory=True))
    result = executor._build_prompt(job)

    assert "基础任务" in result
    assert "历史记忆内容" in result


@pytest.mark.asyncio
async def test_cleanup_job_removes_running_entry():
    """验证 cleanup_job 同时清理 _running_jobs。"""
    from sensenova_claw.kernel.proactive.executor import ProactiveExecutor

    executor = ProactiveExecutor.__new__(ProactiveExecutor)
    executor._job_locks = {"pj-2": asyncio.Lock()}
    executor._running_jobs = {"pj-2"}

    executor.cleanup_job("pj-2")

    assert "pj-2" not in executor._job_locks
    assert "pj-2" not in executor._running_jobs
