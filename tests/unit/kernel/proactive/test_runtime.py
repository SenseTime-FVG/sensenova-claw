"""ProactiveRuntime 单元测试"""

import asyncio
import hashlib
import os
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sensenova_claw.kernel.proactive.models import (
    DeliveryConfig,
    EventTrigger,
    JobState,
    ProactiveJob,
    ProactiveTask,
    SafetyConfig,
    TimeTrigger,
)
from sensenova_claw.kernel.proactive.runtime import ProactiveRuntime


def _make_job(trigger=None, **kwargs) -> ProactiveJob:
    """创建测试用 ProactiveJob。"""
    return ProactiveJob(
        id=kwargs.pop("id", "test-job-1"),
        name=kwargs.pop("name", "test-job"),
        agent_id=kwargs.pop("agent_id", "proactive-agent"),
        enabled=kwargs.pop("enabled", True),
        trigger=trigger or TimeTrigger(every="30m"),
        task=kwargs.pop("task", ProactiveTask(prompt="test prompt")),
        delivery=kwargs.pop("delivery", DeliveryConfig(channels=["web"])),
        safety=kwargs.pop("safety", SafetyConfig()),
        state=kwargs.pop("state", JobState()),
        **kwargs,
    )


def _make_runtime(**overrides) -> ProactiveRuntime:
    """创建带 mock 依赖的 ProactiveRuntime。"""
    bus = MagicMock()
    bus._subscribers = set()
    bus.publish = AsyncMock()
    bus.subscribe = MagicMock()
    bus.subscribe_queue = MagicMock(return_value=asyncio.Queue())
    bus.unsubscribe_queue = MagicMock()
    repo = MagicMock()
    repo.create_proactive_job = AsyncMock()
    repo.get_proactive_job = AsyncMock(return_value=None)
    repo.list_proactive_jobs = AsyncMock(return_value=[])
    repo.update_proactive_job = AsyncMock()
    repo.delete_proactive_job = AsyncMock()
    repo.create_proactive_run = AsyncMock()
    repo.update_proactive_run = AsyncMock()

    agent_runtime = MagicMock()
    agent_runtime.spawn_agent_session = AsyncMock(return_value="turn_123")

    notification_service = MagicMock()
    notification_service.send = AsyncMock()

    defaults = {
        "bus": bus,
        "repo": repo,
        "agent_runtime": agent_runtime,
        "notification_service": notification_service,
    }
    defaults.update(overrides)

    with patch("sensenova_claw.kernel.proactive.runtime.config") as mock_config:
        mock_config.get = lambda path, default=None: {
            "proactive.enabled": True,
            "proactive.max_concurrent_runs": 3,
        }.get(path, default)
        rt = ProactiveRuntime(**defaults)

    return rt


# ---------- Config 加载测试 ----------


def _make_runtime_with_jobs(jobs_list):
    """创建带 proactive.jobs 配置的 runtime。"""
    bus = MagicMock()
    bus._subscribers = set()
    bus.publish = AsyncMock()
    bus.subscribe = MagicMock()
    bus.subscribe_queue = MagicMock(return_value=asyncio.Queue())
    bus.unsubscribe_queue = MagicMock()
    repo = MagicMock()
    repo.create_proactive_job = AsyncMock()
    repo.get_proactive_job = AsyncMock(return_value=None)
    repo.list_proactive_jobs = AsyncMock(return_value=[])
    repo.update_proactive_job = AsyncMock()
    repo.delete_proactive_job = AsyncMock()
    repo.create_proactive_run = AsyncMock()
    repo.update_proactive_run = AsyncMock()

    agent_runtime = MagicMock()
    agent_runtime.spawn_agent_session = AsyncMock(return_value="turn_123")

    notification_service = MagicMock()
    notification_service.send = AsyncMock()

    config_data = {
        "proactive.enabled": True,
        "proactive.max_concurrent_runs": 3,
        "proactive.jobs": jobs_list,
    }

    with patch("sensenova_claw.kernel.proactive.runtime.config") as mock_config:
        mock_config.get = lambda path, default=None: config_data.get(path, default)
        rt = ProactiveRuntime(
            bus=bus, repo=repo,
            agent_runtime=agent_runtime,
            notification_service=notification_service,
        )
    # 让 _load_jobs_from_config 也能读到 jobs
    rt._config_get = lambda path, default=None: config_data.get(path, default)
    with patch("sensenova_claw.kernel.proactive.runtime.config") as mock_config:
        mock_config.get = lambda path, default=None: config_data.get(path, default)
        jobs = rt._load_jobs_from_config()
    return rt, jobs


class TestLoadJobsFromConfig:
    def test_load_time_trigger(self):
        _, jobs = _make_runtime_with_jobs([
            {
                "name": "daily-report",
                "agent_id": "report-agent",
                "trigger": {"kind": "time", "every": "1h"},
                "task": {"prompt": "生成日报"},
                "delivery": {"channels": ["web"]},
            }
        ])

        assert len(jobs) == 1
        job = jobs[0]
        expected_id = f"pj_cfg_{hashlib.md5(b'daily-report').hexdigest()[:12]}"
        assert job.id == expected_id
        assert job.name == "daily-report"
        assert job.agent_id == "report-agent"
        assert isinstance(job.trigger, TimeTrigger)
        assert job.trigger.every == "1h"
        assert job.source == "config"

    def test_load_event_trigger(self):
        _, jobs = _make_runtime_with_jobs([
            {
                "name": "email-handler",
                "trigger": {
                    "kind": "event",
                    "event_type": "email.received",
                    "debounce_ms": 10000,
                },
                "task": {"prompt": "处理邮件"},
            }
        ])

        assert len(jobs) == 1
        assert isinstance(jobs[0].trigger, EventTrigger)
        assert jobs[0].trigger.event_type == "email.received"
        assert jobs[0].trigger.debounce_ms == 10000

    def test_empty_jobs_returns_empty(self):
        _, jobs = _make_runtime_with_jobs([])
        assert jobs == []

    def test_none_jobs_returns_empty(self):
        _, jobs = _make_runtime_with_jobs(None)
        assert jobs == []

    def test_deterministic_id(self):
        """同名 job 应生成相同 ID。"""
        _, jobs1 = _make_runtime_with_jobs([{"name": "my-job", "task": {"prompt": "test"}}])
        _, jobs2 = _make_runtime_with_jobs([{"name": "my-job", "task": {"prompt": "test"}}])
        assert jobs1[0].id == jobs2[0].id


# ---------- 禁用 job 跳过测试 ----------


class TestEvaluateAndExecute:
    @pytest.mark.asyncio
    async def test_skip_disabled_job(self):
        """禁用的 job 不应被执行。"""
        rt = _make_runtime()
        job = _make_job(enabled=False)
        rt._jobs[job.id] = job

        result = await rt._evaluate_and_execute(job)
        assert result is False
        # 不应发布任何事件
        rt._bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_running_job(self):
        """正在运行的 job 不应重复执行。"""
        rt = _make_runtime()
        job = _make_job()
        rt._jobs[job.id] = job
        rt._executor._running_jobs.add(job.id)

        result = await rt._evaluate_and_execute(job)
        assert result is False

    @pytest.mark.asyncio
    async def test_execute_without_condition(self):
        """无条件的 job 应直接启动执行。"""
        rt = _make_runtime()
        job = _make_job(trigger=TimeTrigger(every="30m"))
        rt._jobs[job.id] = job
        rt._executor.execute_job = AsyncMock(return_value=("session-1", "result"))
        result = await rt._evaluate_and_execute(job)
        assert result is True
        # 应发布 PROACTIVE_JOB_TRIGGERED
        assert rt._bus.publish.call_count >= 1
        first_call = rt._bus.publish.call_args_list[0]
        assert first_call[0][0].type == "proactive.job_triggered"


# ---------- 事件索引测试 ----------


class TestEventIndex:
    def test_rebuild_event_index(self):
        """事件索引应包含所有启用的 EventTrigger 的 event_type。"""
        rt = _make_runtime()
        rt._jobs.clear()
        rt._jobs.update({
            "j1": _make_job(id="j1", trigger=EventTrigger(event_type="email.received")),
            "j2": _make_job(id="j2", trigger=EventTrigger(event_type="file.changed")),
            "j3": _make_job(id="j3", trigger=TimeTrigger(every="1h")),
            "j4": _make_job(id="j4", trigger=EventTrigger(event_type="email.received"), enabled=False),
        })
        rt._scheduler.rebuild_event_index()

        assert rt._scheduler._watched_event_types == {"email.received", "file.changed"}

    def test_empty_index_when_no_event_jobs(self):
        rt = _make_runtime()
        rt._jobs.clear()
        rt._jobs.update({
            "j1": _make_job(id="j1", trigger=TimeTrigger(every="1h")),
        })
        rt._scheduler.rebuild_event_index()
        assert rt._scheduler._watched_event_types == set()


# ---------- Safety meta 注入测试 ----------


class TestBuildSessionMeta:
    def test_safety_meta_injected(self):
        """spawn_agent_session 的 meta 应包含安全约束。"""
        rt = _make_runtime()
        job = _make_job(
            safety=SafetyConfig(
                allowed_tools=["bash_command", "read_file"],
                blocked_tools=["write_file"],
                max_tool_calls=5,
                max_llm_calls=3,
                max_duration_ms=60_000,
            ),
        )
        job.task.system_prompt_override = "你是安全助手"

        meta = rt._executor._build_session_meta(job)

        assert meta["agent_id"] == "proactive-agent"
        assert meta["type"] == "proactive"
        assert meta["proactive_job_id"] == job.id
        assert meta["allowed_tools"] == ["bash_command", "read_file"]
        assert meta["blocked_tools"] == ["write_file"]
        assert meta["max_tool_calls"] == 5
        assert meta["max_llm_calls"] == 3
        assert meta["max_duration_ms"] == 60_000
        assert meta["system_prompt_override"] == "你是安全助手"

    def test_no_tool_filters_when_none(self):
        """allowed_tools/blocked_tools 为 None 时不应出现在 meta 中。"""
        rt = _make_runtime()
        job = _make_job(safety=SafetyConfig(allowed_tools=None, blocked_tools=None))

        meta = rt._executor._build_session_meta(job)

        assert "allowed_tools" not in meta
        assert "blocked_tools" not in meta
        assert "max_tool_calls" in meta


# ---------- 自动禁用测试 ----------


class TestAutoDisable:
    @pytest.mark.asyncio
    async def test_auto_disable_after_consecutive_errors(self):
        """连续失败达到阈值后应自动禁用 job。"""
        rt = _make_runtime()
        job = _make_job(safety=SafetyConfig(auto_disable_after_errors=2))
        job.state.consecutive_errors = 1
        rt._jobs[job.id] = job

        await rt._executor._handle_failure(job, "run-1", "sess-1", "test error", int(time.time() * 1000))

        assert job.state.consecutive_errors == 2
        assert job.enabled is False
        rt._repo.update_proactive_job.assert_called()

    @pytest.mark.asyncio
    async def test_no_disable_below_threshold(self):
        """未达到阈值时不应禁用。"""
        rt = _make_runtime()
        job = _make_job(safety=SafetyConfig(auto_disable_after_errors=3))
        job.state.consecutive_errors = 0
        rt._jobs[job.id] = job

        await rt._executor._handle_failure(job, "run-1", "sess-1", "test error", int(time.time() * 1000))

        assert job.state.consecutive_errors == 1
        assert job.enabled is True


# ---------- Prompt 构建测试 ----------


class TestBuildPrompt:
    def test_basic_prompt(self):
        rt = _make_runtime()
        job = _make_job()
        job.task.prompt = "检查系统状态"

        prompt = rt._executor._build_prompt(job)
        assert prompt == "检查系统状态"

    def test_prompt_with_memory(self):
        memory_manager = MagicMock()
        memory_manager.get_context = MagicMock(return_value="上次检查时间: 10:00")

        rt = _make_runtime(memory_manager=memory_manager)
        job = _make_job()
        job.task.prompt = "检查系统状态"
        job.task.use_memory = True

        prompt = rt._executor._build_prompt(job)
        assert "检查系统状态" in prompt
        assert "上次检查时间: 10:00" in prompt


class TestRunAndDeliver:
    @pytest.mark.asyncio
    async def test_delivery_called_on_success(self):
        rt = _make_runtime()
        job = _make_job()
        rt._jobs[job.id] = job
        rt._executor.execute_job = AsyncMock(return_value=("session-1", "执行结果"))
        job.state.last_status = "ok"
        rt._delivery.deliver = AsyncMock()
        await rt._run_and_deliver(job)
        rt._delivery.deliver.assert_called_once_with(job, "session-1", "执行结果")

    @pytest.mark.asyncio
    async def test_delivery_skipped_on_failure(self):
        rt = _make_runtime()
        job = _make_job()
        rt._jobs[job.id] = job
        rt._executor.execute_job = AsyncMock(return_value=("session-1", None))
        job.state.last_status = "error"
        rt._delivery.deliver = AsyncMock()
        await rt._run_and_deliver(job)
        rt._delivery.deliver.assert_not_called()

    @pytest.mark.asyncio
    async def test_delivery_skipped_when_no_result(self):
        rt = _make_runtime()
        job = _make_job()
        rt._jobs[job.id] = job
        rt._executor.execute_job = AsyncMock(return_value=("session-1", ""))
        job.state.last_status = "ok"
        rt._delivery.deliver = AsyncMock()
        await rt._run_and_deliver(job)
        # 空字符串 result 是 falsy，不应调用 delivery
        rt._delivery.deliver.assert_not_called()
