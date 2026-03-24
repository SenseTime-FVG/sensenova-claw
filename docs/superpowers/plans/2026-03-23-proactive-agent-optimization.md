# Proactive Agent 优化实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 优化 ProactiveRuntime——删除 ConditionTrigger、拆分 runtime 为 scheduler+executor、修复并发安全和可靠性问题、添加偏好发现 Job 配置。

**Architecture:** 将 618 行的 `runtime.py` 拆分为 scheduler（调度）+ executor（执行）+ runtime（入口），删除 ConditionTrigger 简化模型，在 executor 层加并发锁和超时处理，在 delivery 层加重试和 summary_prompt 支持。偏好发现作为普通 config job 配置。

**Tech Stack:** Python 3.12, asyncio, SQLite, FastAPI

**Spec:** `docs/superpowers/specs/2026-03-23-proactive-agent-optimization-design.md`

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `agentos/kernel/proactive/models.py` | 修改 | 删除 ConditionTrigger、condition 字段、相关序列化 |
| `agentos/kernel/proactive/triggers.py` | 修改 | 删除 condition 评估函数，删除 ConditionTrigger 分支 |
| `agentos/kernel/proactive/scheduler.py` | 新建 | 从 runtime.py 提取调度逻辑 |
| `agentos/kernel/proactive/executor.py` | 新建 | 从 runtime.py 提取执行逻辑，加并发锁和超时处理 |
| `agentos/kernel/proactive/delivery.py` | 修改 | 加重试和 summary_prompt 支持 |
| `agentos/kernel/proactive/runtime.py` | 重写 | 瘦身为入口，组合 scheduler+executor+delivery |
| `agentos/capabilities/tools/proactive_tools.py` | 修改 | 删除 condition 字段，加 safety 参数，修复 await bug |
| `agentos/kernel/events/types.py` | 修改 | 删除 PROACTIVE_CONDITION_EVALUATED |
| `tests/integration/test_proactive_runtime.py` | 修改 | 更新测试适配新结构 |
| `tests/unit/test_proactive_models.py` | 新建 | models 单元测试 |
| `tests/unit/test_proactive_scheduler.py` | 新建 | scheduler 单元测试 |
| `tests/unit/test_proactive_executor.py` | 新建 | executor 单元测试 |
| `tests/unit/test_proactive_delivery.py` | 新建 | delivery 单元测试 |
| `config.yml` | 修改 | 添加偏好发现 Job 配置 |

---

### Task 1: 删除 ConditionTrigger 和 condition 字段

**Files:**
- Modify: `agentos/kernel/proactive/models.py:30-57,131-179`
- Modify: `agentos/kernel/proactive/triggers.py:11-21,44-59`
- Modify: `agentos/kernel/events/types.py:65`
- Test: `tests/unit/test_proactive_models.py`

- [ ] **Step 1: 写 models 单元测试（删除前的基线）**

```python
# tests/unit/test_proactive_models.py
"""ProactiveJob 模型单元测试。"""
import json
import pytest
from agentos.kernel.proactive.models import (
    TimeTrigger,
    EventTrigger,
    ProactiveTask,
    DeliveryConfig,
    SafetyConfig,
    JobState,
    ProactiveJob,
    trigger_to_json,
    trigger_from_json,
    job_to_db_row,
    job_from_db_row,
    parse_duration_ms,
)


def test_parse_duration_ms():
    assert parse_duration_ms("5m") == 300_000
    assert parse_duration_ms("1h") == 3_600_000
    assert parse_duration_ms("30s") == 30_000
    assert parse_duration_ms("2d") == 172_800_000


def test_time_trigger_serialization_roundtrip():
    trigger = TimeTrigger(cron="0 9 * * *")
    json_str = trigger_to_json(trigger)
    restored = trigger_from_json(json_str)
    assert isinstance(restored, TimeTrigger)
    assert restored.cron == "0 9 * * *"
    assert restored.every is None


def test_time_trigger_every_serialization():
    trigger = TimeTrigger(every="5m")
    json_str = trigger_to_json(trigger)
    restored = trigger_from_json(json_str)
    assert isinstance(restored, TimeTrigger)
    assert restored.every == "5m"


def test_event_trigger_serialization_roundtrip():
    trigger = EventTrigger(event_type="user.input", filter={"key": "val"}, debounce_ms=3000)
    json_str = trigger_to_json(trigger)
    restored = trigger_from_json(json_str)
    assert isinstance(restored, EventTrigger)
    assert restored.event_type == "user.input"
    assert restored.filter == {"key": "val"}
    assert restored.debounce_ms == 3000


def test_trigger_from_json_unknown_kind_raises():
    with pytest.raises(ValueError, match="Unknown trigger kind"):
        trigger_from_json(json.dumps({"kind": "unknown"}))


def test_job_db_roundtrip():
    job = ProactiveJob(
        id="pj-test",
        name="测试",
        trigger=TimeTrigger(cron="0 2 * * *"),
        task=ProactiveTask(prompt="测试 prompt", use_memory=True),
        delivery=DeliveryConfig(channels=["web"]),
        safety=SafetyConfig(max_llm_calls=5, max_duration_ms=600000),
        state=JobState(),
    )
    row = job_to_db_row(job)
    restored = job_from_db_row(row)
    assert restored.id == "pj-test"
    assert restored.name == "测试"
    assert isinstance(restored.trigger, TimeTrigger)
    assert restored.trigger.cron == "0 2 * * *"
    assert restored.task.use_memory is True
    assert restored.safety.max_llm_calls == 5
```

- [ ] **Step 2: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/test_proactive_models.py -v`
Expected: ALL PASS

- [ ] **Step 3: 删除 ConditionTrigger 和 condition 字段**

在 `models.py` 中：
1. 删除 `ConditionTrigger` 类（lines 49-54）
2. 删除 `TimeTrigger.condition` 字段（line 36）
3. 删除 `EventTrigger.condition` 字段（line 46）
4. 更新 `Trigger` 类型别名（line 57）为 `Trigger = TimeTrigger | EventTrigger`
5. 在 `trigger_to_json()` 中：删除 `ConditionTrigger` 分支（lines 148-154），删除 `TimeTrigger`/`EventTrigger` 的 `condition` 写入（lines 137, 146）
6. 在 `trigger_from_json()` 中：删除 `kind == "condition"` 分支（lines 173-179），删除 `condition` 读取（lines 165, 172）

在 `triggers.py` 中：
1. 删除 `build_condition_prompt()` 函数（lines 44-54）
2. 删除 `parse_condition_response()` 函数（lines 57-59）
3. 在 `compute_next_fire_ms()` 中删除 `ConditionTrigger` 分支（lines 19-20）
4. 更新 imports，移除 `ConditionTrigger`

在 `events/types.py` 中：
1. 删除 `PROACTIVE_CONDITION_EVALUATED` 常量（line 65）

**同步清理 `runtime.py`**（防止 import 链断裂）：
1. 删除 `ConditionTrigger` import（line 35）
2. 删除 `build_condition_prompt`, `parse_condition_response` import（lines 48, 52）
3. 删除 `PROACTIVE_CONDITION_EVALUATED` import（line 26）
4. 删除 `_get_condition()` 方法（lines 416-423）
5. 删除 `_evaluate_condition()` 方法（lines 425-436）
6. 在 `_evaluate_and_execute()` 中删除 condition 评估逻辑（lines 390-411 中的 condition 分支），简化为直接 spawn `_execute_job`
7. 在 `_on_timer()` 中删除 `ConditionTrigger` isinstance 检查（line 332）
8. 在 `_parse_job_config()` 中删除 `kind: "condition"` 解析分支（lines 238-243）

**同步清理 `proactive_tools.py`**：
1. 删除 `ConditionTrigger` import（line 16）
2. 在 `_parse_trigger()` 中删除 `kind == "condition"` 分支

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/test_proactive_models.py tests/integration/test_proactive_runtime.py -v`
Expected: ALL PASS（models 测试通过，集成测试因 runtime.py 已同步清理也能 import）

- [ ] **Step 5: 提交**

```bash
git add agentos/kernel/proactive/models.py agentos/kernel/proactive/triggers.py agentos/kernel/events/types.py agentos/kernel/proactive/runtime.py agentos/capabilities/tools/proactive_tools.py tests/unit/test_proactive_models.py
git commit -m "refactor: 删除 ConditionTrigger 和 condition 字段，简化触发器模型"
```

---

### Task 2: 更新 CreateProactiveJobTool（safety 参数 + await 修复）

**Files:**
- Modify: `agentos/capabilities/tools/proactive_tools.py:50-134`

- [ ] **Step 1: 更新 `CreateProactiveJobTool`**

1. 新增 `safety` 参数到 `CreateProactiveJobTool.parameters`，支持 `max_llm_calls`（int）和 `max_duration_ms`（int）
2. 在 `CreateProactiveJobTool.execute()` 中解析 `safety` 参数构建 `SafetyConfig`，替代硬编码的 `SafetyConfig()`
3. 修复 `ListProactiveJobsTool.execute()` 中 `self._runtime.list_jobs()` 缺少 `await`

- [ ] **Step 2: 运行现有集成测试确认不破坏**

Run: `python3 -m pytest tests/integration/test_proactive_runtime.py -v`
Expected: ALL PASS

- [ ] **Step 3: 提交**

```bash
git add agentos/capabilities/tools/proactive_tools.py
git commit -m "refactor: 更新 proactive tools，删除 condition 字段，添加 safety 参数，修复 await bug"
```

---

### Task 3: 提取 scheduler.py

**Files:**
- Create: `agentos/kernel/proactive/scheduler.py`
- Modify: `agentos/kernel/proactive/runtime.py`
- Test: `tests/unit/test_proactive_scheduler.py`

- [ ] **Step 1: 写 scheduler 单元测试**

```python
# tests/unit/test_proactive_scheduler.py
"""ProactiveScheduler 单元测试。"""
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock

from agentos.kernel.proactive.models import (
    ProactiveJob, TimeTrigger, EventTrigger,
    ProactiveTask, DeliveryConfig, SafetyConfig, JobState,
)


def _make_job(trigger, **kwargs):
    defaults = dict(
        id="pj-sched-1",
        name="调度测试",
        agent_id="proactive-agent",
        trigger=trigger,
        task=ProactiveTask(prompt="测试"),
        delivery=DeliveryConfig(channels=["web"]),
        safety=SafetyConfig(max_duration_ms=5000),
        state=JobState(),
    )
    defaults.update(kwargs)
    return ProactiveJob(**defaults)


@pytest.mark.asyncio
async def test_cleanup_debounce_removes_expired():
    """验证 debounce 字典清理移除过期条目。"""
    from agentos.kernel.proactive.scheduler import ProactiveScheduler

    scheduler = ProactiveScheduler.__new__(ProactiveScheduler)
    scheduler._last_event_fires = {
        "old-job": int(time.time() * 1000) - 7_200_000,  # 2 小时前
        "recent-job": int(time.time() * 1000) - 60_000,  # 1 分钟前
    }

    scheduler._cleanup_debounce()

    assert "old-job" not in scheduler._last_event_fires
    assert "recent-job" in scheduler._last_event_fires
```

- [ ] **Step 2: 创建 `scheduler.py`**

从 `runtime.py` 提取以下方法到 `ProactiveScheduler` 类：
- `_arm_timer()` (lines 298-302)
- `_delayed_timer()` (lines 304-310)
- `_compute_timer_delay()` (lines 312-323)
- `_on_timer()` (lines 325-343)
- `_event_loop()` (lines 347-371)
- `_rebuild_event_index()` (lines 289-294)
- 新增 `_cleanup_debounce()` 方法

`ProactiveScheduler.__init__` 接收：
- `bus`: PublicEventBus
- `jobs`: dict 引用（与 runtime 共享）
- `running_jobs`: set 引用
- `max_concurrent`: int
- `on_trigger`: 回调函数（替代直接调用 `_evaluate_and_execute`）

- [ ] **Step 3: 运行测试**

Run: `python3 -m pytest tests/unit/test_proactive_scheduler.py -v`
Expected: ALL PASS

- [ ] **Step 4: 提交**

```bash
git add agentos/kernel/proactive/scheduler.py tests/unit/test_proactive_scheduler.py
git commit -m "refactor: 提取 ProactiveScheduler，负责触发调度"
```

---

### Task 4: 提取 executor.py（含并发锁和超时处理）

**Files:**
- Create: `agentos/kernel/proactive/executor.py`
- Test: `tests/unit/test_proactive_executor.py`

- [ ] **Step 1: 写 executor 单元测试**

```python
# tests/unit/test_proactive_executor.py
"""ProactiveExecutor 单元测试。"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from agentos.kernel.proactive.models import (
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
    from agentos.kernel.proactive.executor import ProactiveExecutor

    bus = MagicMock()
    bus.publish = AsyncMock()
    bus._subscribers = set()
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

    # spawn 不应被调用
    agent_runtime.spawn_agent_session.assert_not_called()


@pytest.mark.asyncio
async def test_execute_job_handles_timeout():
    """验证 _wait_for_completion 超时时走失败路径。"""
    from agentos.kernel.proactive.executor import ProactiveExecutor

    bus = MagicMock()
    bus.publish = AsyncMock()
    bus._subscribers = set()
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

    # _wait_for_completion 会超时（100ms 内不会有事件）
    await executor.execute_job(job)

    assert job.state.last_status in ("error", "timeout")
    assert job.state.consecutive_errors >= 1


@pytest.mark.asyncio
async def test_lock_cleanup_on_remove():
    """验证 job 删除时清理 lock。"""
    from agentos.kernel.proactive.executor import ProactiveExecutor

    executor = ProactiveExecutor.__new__(ProactiveExecutor)
    executor._job_locks = {"pj-1": asyncio.Lock()}
    executor._running_jobs = set()

    executor.cleanup_job("pj-1")

    assert "pj-1" not in executor._job_locks
```

- [ ] **Step 2: 创建 `executor.py`**

从 `runtime.py` 提取以下方法到 `ProactiveExecutor` 类：
- `_execute_job()` (lines 438-518) → 重命名为 `execute_job()`，加 `asyncio.Lock` 保护
- `_handle_failure()` (lines 520-556)
- `_build_prompt()` (lines 560-570)
- `_build_session_meta()` (lines 572-589)
- `_wait_for_completion()` (lines 591-605) → 改为返回 `str | None`，超时返回 `None`
- `_persist_job_state()` (lines 607-617)
- 新增 `cleanup_job(job_id)` 清理 `_job_locks`

`ProactiveExecutor.__init__` 接收：
- `bus`: PublicEventBus
- `repo`: Repository
- `agent_runtime`: AgentRuntime
- `memory_manager`: MemoryManager | None

关键改动：
1. `execute_job()` 中用 `asyncio.Lock` 包裹整个执行流程
2. `_wait_for_completion()` 返回 `None` 时，`execute_job()` 走 `_handle_failure` 路径
3. `_running_jobs` 和 `_job_locks` 作为实例属性
4. `_wait_for_completion()` 增加心跳超时检测：记录最后一次收到任意事件的时间，如果超过 `max_duration_ms / 3` 没有收到该 session 的任何事件，提前返回 `None`（判定为异常）

- [ ] **Step 3: 运行测试**

Run: `python3 -m pytest tests/unit/test_proactive_executor.py -v`
Expected: ALL PASS

- [ ] **Step 4: 提交**

```bash
git add agentos/kernel/proactive/executor.py tests/unit/test_proactive_executor.py
git commit -m "refactor: 提取 ProactiveExecutor，含并发锁和超时处理"
```

---

### Task 5: 改进 delivery.py（重试 + summary_prompt）

**Files:**
- Modify: `agentos/kernel/proactive/delivery.py`
- Test: `tests/unit/test_proactive_delivery.py`

- [ ] **Step 1: 写 delivery 单元测试**

```python
# tests/unit/test_proactive_delivery.py
"""ProactiveDelivery 单元测试。"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from agentos.kernel.proactive.delivery import ProactiveDelivery
from agentos.kernel.proactive.models import (
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

    # 不应抛异常（第三次成功）
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

    # Mock LLM provider
    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(return_value={"content": "摘要内容"})

    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            "agentos.kernel.proactive.delivery.create_llm_provider",
            lambda: mock_provider,
        )
        await delivery.deliver(job, "sess-1", "很长的原始结果...")

    ns.send.assert_called_once()
    notification = ns.send.call_args.args[0]
    assert "摘要内容" in notification.body
```

- [ ] **Step 2: 实现 delivery 改进**

在 `delivery.py` 中：
1. 通知发送部分加重试循环（3 次，间隔 3 秒）
2. 在 `deliver()` 中，发送通知前检查 `job.delivery.summary_prompt`：
   - 非空：调用 LLM 做摘要，用摘要替代原始 result 作为通知 body
   - 空/None：保持原样
3. summary LLM 调用失败时降级为原始 result

- [ ] **Step 3: 运行测试**

Run: `python3 -m pytest tests/unit/test_proactive_delivery.py -v`
Expected: ALL PASS

- [ ] **Step 4: 提交**

```bash
git add agentos/kernel/proactive/delivery.py tests/unit/test_proactive_delivery.py
git commit -m "feat: delivery 加重试和 summary_prompt 支持"
```

---

### Task 6: 重写 runtime.py 为入口层

**Files:**
- Modify: `agentos/kernel/proactive/runtime.py`
- Modify: `tests/integration/test_proactive_runtime.py`

- [ ] **Step 1: 重写 `runtime.py`**

`ProactiveRuntime` 瘦身为组合层：
- `__init__`: 创建 `ProactiveScheduler` 和 `ProactiveExecutor` 实例
- `start()`: 加载 jobs，启动 scheduler
- `stop()`: 停止 scheduler
- `add_job()` / `remove_job()` / `set_job_enabled()` / `list_jobs()`: 维护 `_jobs` 字典，调用 repo，通知 scheduler 重建索引
- `remove_job()` 中同步调用 `executor.cleanup_job()` 清理 lock
- `_evaluate_and_execute()`: 简化为发布 TRIGGERED 事件 + 调用 `executor.execute_job()`（删除 condition 评估逻辑）
- `_load_all_jobs()` / `_load_jobs_from_config()` / `_parse_job_config()`: 保留在 runtime 中（job 加载是入口职责），删除 `kind: "condition"` 解析分支

关键：`ProactiveScheduler` 的 `on_trigger` 回调指向 `runtime._evaluate_and_execute`。

- [ ] **Step 2: 更新集成测试**

更新 `tests/integration/test_proactive_runtime.py`：
1. 移除 `ConditionTrigger` 相关 import
2. 测试中的 `_make_job` 不再使用 condition 字段
3. 确保 `test_execute_job_success` 等测试适配新的 executor 调用路径
4. 如果测试直接调用 `runtime._execute_job`，改为调用 `runtime._executor.execute_job`

- [ ] **Step 3: 运行全部测试**

Run: `python3 -m pytest tests/unit/test_proactive_models.py tests/unit/test_proactive_scheduler.py tests/unit/test_proactive_executor.py tests/unit/test_proactive_delivery.py tests/integration/test_proactive_runtime.py -v`
Expected: ALL PASS

- [ ] **Step 4: 提交**

```bash
git add agentos/kernel/proactive/runtime.py tests/integration/test_proactive_runtime.py
git commit -m "refactor: 重写 ProactiveRuntime 为入口层，组合 scheduler+executor+delivery"
```

---

### Task 7: 更新 gateway 集成和 __init__.py

**Files:**
- Modify: `agentos/app/gateway/main.py:212-224`
- Modify: `agentos/kernel/proactive/__init__.py`

- [ ] **Step 1: 更新 `__init__.py` 导出**

确保 `__init__.py` 导出 `ProactiveRuntime`、`ProactiveScheduler`、`ProactiveExecutor`、`ProactiveDelivery`。

- [ ] **Step 2: 验证 gateway 集成**

`gateway/main.py` 中 `ProactiveRuntime` 的构造参数不变（bus, repo, agent_runtime, notification_service, gateway, memory_manager），确认无需修改 gateway 代码。如果 `ProactiveRuntime.__init__` 签名变了，同步更新 gateway。

- [ ] **Step 3: 运行全部测试**

Run: `python3 -m pytest tests/ -q --ignore=tests/e2e`
Expected: ALL PASS

- [ ] **Step 4: 提交**

```bash
git add agentos/kernel/proactive/__init__.py agentos/app/gateway/main.py
git commit -m "chore: 更新 proactive 模块导出和 gateway 集成"
```

---

### Task 8: 添加偏好发现 Job 配置

**Files:**
- Modify: `config.yml`

- [ ] **Step 1: 在 `config.yml` 中添加偏好发现 Job**

在 `proactive.jobs` 列表中添加偏好发现 job 配置（完整 YAML 见 spec 1.2 节）。

关键配置：
```yaml
proactive:
  enabled: true
  jobs:
    - name: "偏好发现与推送管理"
      agent_id: "proactive-agent"
      trigger:
        kind: time
        cron: "0 2 * * *"
      task:
        prompt: |
          你是偏好发现助手。请执行以下步骤：
          ...（完整 prompt 见 spec）
        use_memory: true
      safety:
        max_llm_calls: 5
        max_duration_ms: 600000
      delivery:
        channels: ["web"]
```

- [ ] **Step 2: 验证配置加载**

Run: `python3 -c "from agentos.platform.config.config import Config; c = Config(); print(c.get('proactive.jobs', []))"`
Expected: 输出包含偏好发现 job 的配置列表

- [ ] **Step 3: 提交**

```bash
git add config.yml
git commit -m "feat: 添加偏好发现与推送管理 proactive job 配置"
```

---

### Task 9: 最终集成验证

- [ ] **Step 1: 运行全部单元测试**

Run: `python3 -m pytest tests/unit/ -v`
Expected: ALL PASS

- [ ] **Step 2: 运行集成测试**

Run: `python3 -m pytest tests/integration/test_proactive_runtime.py -v`
Expected: ALL PASS

- [ ] **Step 3: 运行全量测试（排除 e2e）**

Run: `python3 -m pytest tests/ -q --ignore=tests/e2e`
Expected: ALL PASS，无新增失败

- [ ] **Step 4: 最终提交（如有遗漏修复）**

```bash
git add -A
git commit -m "fix: 最终集成修复"
```
