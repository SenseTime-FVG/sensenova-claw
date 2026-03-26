# Turn-End 会话推荐 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每次对话 turn 结束后，异步生成 3-5 条推荐展示在 Dashboard 看板，用户点击可跳转到对应会话并填入输入框。

**Architecture:** 基于现有 ProactiveJob EventTrigger 机制，监听 `agent.step_completed` 事件，在原始会话中注入推荐请求（复用 KV cache），解析 LLM 返回的 JSON 推荐列表，通过 `proactive_result` 事件推送到前端 ProactiveAgentPanel。

**Tech Stack:** Python 3.12 / FastAPI / asyncio / Next.js 14 / TypeScript / WebSocket

**Spec:** `docs/superpowers/specs/2026-03-26-turn-end-recommendation-design.md`

---

## File Structure

### 后端修改

| 文件 | 职责 |
|------|------|
| `sensenova_claw/kernel/proactive/models.py` | EventTrigger 新增 `exclude_payload`，DeliveryConfig 新增 `recommendation_type` |
| `sensenova_claw/kernel/proactive/triggers.py` | `is_event_match` 增加排除逻辑，`should_debounce` 支持 per-session key |
| `sensenova_claw/kernel/proactive/scheduler.py` | `_on_trigger` 透传 EventEnvelope，debounce key 改为 `job_id:session_id` |
| `sensenova_claw/kernel/proactive/executor.py` | 新增注入模式（`send_user_input` 到源会话），按 `turn_id` 等待完成，解析推荐 JSON |
| `sensenova_claw/kernel/proactive/delivery.py` | `deliver()` 增加 `source_session_id` 和 `items` 参数 |
| `sensenova_claw/kernel/proactive/runtime.py` | 调用链透传 `trigger_event`，内置 job 注册，配置读取 |
| `sensenova_claw/kernel/runtime/workers/agent_worker.py` | `agent.step_completed` payload 透传 turn meta 中的 `source` 字段 |

### 后端测试

| 文件 | 职责 |
|------|------|
| `tests/unit/kernel/proactive/test_triggers.py` | `exclude_payload` 过滤、per-session debounce |
| `tests/unit/kernel/proactive/test_delivery.py` | `deliver()` 新参数透传 |
| `tests/unit/kernel/proactive/test_models.py` | 新字段序列化 |
| `tests/unit/kernel/proactive/test_executor.py` | 注入模式、JSON 解析 |
| `tests/unit/kernel/proactive/test_runtime.py` | 内置 job 注册、trigger_event 透传 |

### 前端修改

| 文件 | 职责 |
|------|------|
| `sensenova_claw/app/web/contexts/ChatSessionContext.tsx` | `recommendations` state、`prefillInput`、`proactive_result` 处理 |
| `sensenova_claw/app/web/hooks/useDashboardData.ts` | 推荐数据聚合（合并、过期、上限） |
| `sensenova_claw/app/web/components/dashboard/ProactiveAgentPanel.tsx` | 推荐卡片渲染、点击跳转 |
| `sensenova_claw/app/web/components/dashboard/Dashboard.tsx` | 传递推荐点击回调 |

---

## Task 1: EventTrigger 模型扩展 — exclude_payload 字段

**Files:**
- Modify: `sensenova_claw/kernel/proactive/models.py:38-44` (EventTrigger dataclass)
- Modify: `sensenova_claw/kernel/proactive/models.py:121-154` (trigger 序列化)
- Test: `tests/unit/kernel/proactive/test_triggers.py`
- Test: `tests/unit/kernel/proactive/test_models.py`

- [ ] **Step 1: 写失败测试 — exclude_payload 过滤**

```python
# tests/unit/kernel/proactive/test_triggers.py — 在 TestEventMatch 类中新增

def test_exclude_payload_blocks_match(self):
    trigger = EventTrigger(
        event_type="agent.step_completed",
        exclude_payload={"source": "recommendation"},
    )
    # 带 source=recommendation 的事件应被排除
    assert is_event_match(trigger, "agent.step_completed", {"source": "recommendation"}) is False

def test_exclude_payload_allows_normal(self):
    trigger = EventTrigger(
        event_type="agent.step_completed",
        exclude_payload={"source": "recommendation"},
    )
    # 不带 source 或 source 不同的事件应通过
    assert is_event_match(trigger, "agent.step_completed", {}) is True
    assert is_event_match(trigger, "agent.step_completed", {"source": "user"}) is True

def test_exclude_payload_none_no_effect(self):
    trigger = EventTrigger(event_type="agent.step_completed")
    assert is_event_match(trigger, "agent.step_completed", {"source": "recommendation"}) is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/kernel/proactive/test_triggers.py::TestEventMatch::test_exclude_payload_blocks_match -v`
Expected: FAIL — `EventTrigger` 没有 `exclude_payload` 字段

- [ ] **Step 3: 实现 EventTrigger.exclude_payload 字段**

```python
# sensenova_claw/kernel/proactive/models.py — EventTrigger dataclass
@dataclass
class EventTrigger:
    kind: Literal["event"] = "event"
    event_type: str = ""
    filter: dict | None = None
    debounce_ms: int = 5000
    exclude_payload: dict | None = None  # 新增
```

- [ ] **Step 4: 实现 is_event_match 排除逻辑**

```python
# sensenova_claw/kernel/proactive/triggers.py — is_event_match 函数
def is_event_match(trigger: EventTrigger, event_type: str, payload: dict) -> bool:
    """检查事件是否匹配 EventTrigger。"""
    if trigger.event_type != event_type:
        return False
    if trigger.filter:
        for k, v in trigger.filter.items():
            if payload.get(k) != v:
                return False
    if trigger.exclude_payload:
        for k, v in trigger.exclude_payload.items():
            if payload.get(k) == v:
                return False
    return True
```

- [ ] **Step 5: 更新 trigger 序列化函数**

```python
# sensenova_claw/kernel/proactive/models.py — trigger_to_json 中 EventTrigger 分支
# 在序列化 dict 中增加 exclude_payload
if isinstance(trigger, EventTrigger):
    d = {
        "kind": "event",
        "event_type": trigger.event_type,
        "filter": trigger.filter,
        "debounce_ms": trigger.debounce_ms,
        "exclude_payload": trigger.exclude_payload,
    }

# trigger_from_json 中 event 分支
elif kind == "event":
    return EventTrigger(
        event_type=d.get("event_type", ""),
        filter=d.get("filter"),
        debounce_ms=d.get("debounce_ms", 5000),
        exclude_payload=d.get("exclude_payload"),
    )
```

- [ ] **Step 6: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/kernel/proactive/test_triggers.py::TestEventMatch -v`
Expected: ALL PASS

- [ ] **Step 7: 写序列化往返测试**

```python
# tests/unit/kernel/proactive/test_models.py — 新增
from sensenova_claw.kernel.proactive.models import (
    EventTrigger, trigger_to_json, trigger_from_json,
)

def test_event_trigger_exclude_payload_roundtrip():
    trigger = EventTrigger(
        event_type="agent.step_completed",
        exclude_payload={"source": "recommendation"},
    )
    json_str = trigger_to_json(trigger)
    restored = trigger_from_json(json_str)
    assert isinstance(restored, EventTrigger)
    assert restored.exclude_payload == {"source": "recommendation"}
```

- [ ] **Step 8: 运行序列化测试确认通过**

Run: `python3 -m pytest tests/unit/kernel/proactive/test_models.py::test_event_trigger_exclude_payload_roundtrip -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add sensenova_claw/kernel/proactive/models.py sensenova_claw/kernel/proactive/triggers.py tests/unit/kernel/proactive/test_triggers.py tests/unit/kernel/proactive/test_models.py
git commit -m "feat(proactive): add exclude_payload to EventTrigger for self-trigger prevention"
```

---

## Task 2: DeliveryConfig 模型扩展 — recommendation_type 字段

**Files:**
- Modify: `sensenova_claw/kernel/proactive/models.py:64-69` (DeliveryConfig)
- Modify: `sensenova_claw/kernel/proactive/models.py:173-186` (delivery 序列化)
- Test: `tests/unit/kernel/proactive/test_models.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/kernel/proactive/test_models.py — 新增
from sensenova_claw.kernel.proactive.models import (
    DeliveryConfig, _delivery_to_dict, _delivery_from_dict,
)

def test_delivery_config_recommendation_type_roundtrip():
    dc = DeliveryConfig(channels=["web"], recommendation_type="turn_end")
    d = _delivery_to_dict(dc)
    assert d["recommendation_type"] == "turn_end"
    restored = _delivery_from_dict(d)
    assert restored.recommendation_type == "turn_end"

def test_delivery_config_recommendation_type_default_none():
    dc = DeliveryConfig(channels=["web"])
    assert dc.recommendation_type is None
    d = _delivery_to_dict(dc)
    restored = _delivery_from_dict(d)
    assert restored.recommendation_type is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/kernel/proactive/test_models.py::test_delivery_config_recommendation_type_roundtrip -v`
Expected: FAIL — `DeliveryConfig` 没有 `recommendation_type`

- [ ] **Step 3: 实现 DeliveryConfig.recommendation_type**

```python
# sensenova_claw/kernel/proactive/models.py
@dataclass
class DeliveryConfig:
    channels: list[str] = field(default_factory=list)
    feishu_target: str | None = None
    summary_prompt: str | None = None
    recommendation_type: str | None = None  # 新增
```

- [ ] **Step 4: 更新序列化函数**

```python
# _delivery_to_dict
def _delivery_to_dict(delivery: DeliveryConfig) -> dict:
    return {
        "channels": delivery.channels,
        "feishu_target": delivery.feishu_target,
        "summary_prompt": delivery.summary_prompt,
        "recommendation_type": delivery.recommendation_type,
    }

# _delivery_from_dict
def _delivery_from_dict(d: dict) -> DeliveryConfig:
    return DeliveryConfig(
        channels=d.get("channels", []),
        feishu_target=d.get("feishu_target"),
        summary_prompt=d.get("summary_prompt"),
        recommendation_type=d.get("recommendation_type"),
    )
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/kernel/proactive/test_models.py -v -k "delivery_config_recommendation"`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add sensenova_claw/kernel/proactive/models.py tests/unit/kernel/proactive/test_models.py
git commit -m "feat(proactive): add recommendation_type to DeliveryConfig"
```

---

## Task 3: Debounce 改为 per-session 作用域

**Files:**
- Modify: `sensenova_claw/kernel/proactive/triggers.py:33-39` (should_debounce)
- Modify: `sensenova_claw/kernel/proactive/scheduler.py:150-152` (_event_loop debounce 调用)
- Test: `tests/unit/kernel/proactive/test_triggers.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/kernel/proactive/test_triggers.py — TestDebounce 类中新增

def test_per_session_debounce_independent(self):
    """不同 session 的同一 job 不应互相 debounce。"""
    now_ms = int(time.time() * 1000)
    last_fires = {"job-1:session-A": now_ms - 2000}
    # session-A 在窗口内，应 debounce
    assert should_debounce("job-1:session-A", 5000, last_fires) is True
    # session-B 没有记录，不应 debounce
    assert should_debounce("job-1:session-B", 5000, last_fires) is False
```

- [ ] **Step 2: 运行测试确认通过**

`should_debounce` 本身是纯函数，key 由调用方组装。这个测试验证的是 key 格式的语义，应该直接通过。

Run: `python3 -m pytest tests/unit/kernel/proactive/test_triggers.py::TestDebounce::test_per_session_debounce_independent -v`
Expected: PASS（函数本身不需要改，改的是调用方传入的 key）

- [ ] **Step 3: 修改 scheduler._event_loop 中的 debounce key**

```python
# sensenova_claw/kernel/proactive/scheduler.py — _event_loop 方法中
# 原来:
#   if should_debounce(job.id, job.trigger.debounce_ms, self._last_event_fires):
#       continue
#   self._last_event_fires[job.id] = int(time.time() * 1000)
# 改为:
debounce_key = f"{job.id}:{event.session_id}"
if should_debounce(debounce_key, job.trigger.debounce_ms, self._last_event_fires):
    continue
self._last_event_fires[debounce_key] = int(time.time() * 1000)
```

- [ ] **Step 4: 运行全部 trigger 测试确认无回归**

Run: `python3 -m pytest tests/unit/kernel/proactive/test_triggers.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add sensenova_claw/kernel/proactive/scheduler.py tests/unit/kernel/proactive/test_triggers.py
git commit -m "feat(proactive): per-session debounce for EventTrigger jobs"
```

---

## Task 4: 调用链透传 trigger_event（Scheduler → Runtime → Executor）

**Files:**
- Modify: `sensenova_claw/kernel/proactive/scheduler.py:33-45,136-160` (构造函数 callback 类型、_event_loop)
- Modify: `sensenova_claw/kernel/proactive/runtime.py:47-79,154-174` (构造函数、_evaluate_and_execute、_run_and_deliver)
- Modify: `sensenova_claw/kernel/proactive/executor.py:58-73` (execute_job 签名)
- Test: `tests/unit/kernel/proactive/test_runtime.py`

- [ ] **Step 1: 写失败测试 — trigger_event 透传到 executor**

```python
# tests/unit/kernel/proactive/test_runtime.py — 新增
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.proactive.models import (
    ProactiveJob, EventTrigger, ProactiveTask, DeliveryConfig, SafetyConfig, JobState,
)

@pytest.mark.asyncio
async def test_evaluate_and_execute_passes_trigger_event():
    """_evaluate_and_execute 应将 trigger_event 透传到 _run_and_deliver。"""
    # 需要验证 runtime._run_and_deliver 被调用时携带 trigger_event
    # 具体 mock 结构取决于现有 test_runtime.py 的 fixture 模式
    pass  # 占位，实现时根据现有 fixture 补全
```

- [ ] **Step 2: 修改 Scheduler 构造函数 callback 类型和 _event_loop**

```python
# sensenova_claw/kernel/proactive/scheduler.py
# 构造函数中 on_trigger 参数类型改为:
on_trigger: Callable[[ProactiveJob, EventEnvelope | None], Awaitable[bool]]

# _event_loop 中调用改为:
await self._on_trigger(job, event)  # 原来是 await self._on_trigger(job)

# _on_timer 中调用改为:
await self._on_trigger(job, None)  # TimeTrigger 没有触发事件
```

- [ ] **Step 3: 修改 Runtime._evaluate_and_execute 和 _run_and_deliver**

```python
# sensenova_claw/kernel/proactive/runtime.py
async def _evaluate_and_execute(self, job: ProactiveJob, trigger_event: EventEnvelope | None = None) -> bool:
    """调度器回调：发布触发事件，委托 executor 执行。"""
    if not job.enabled or job.id in self._executor._running_jobs:
        return False
    await self._bus.publish(EventEnvelope(
        type=PROACTIVE_JOB_TRIGGERED,
        session_id=trigger_event.session_id if trigger_event else "system",
        agent_id=job.agent_id,
        source="proactive",
        payload={"job_id": job.id, "job_name": job.name},
    ))
    asyncio.create_task(self._run_and_deliver(job, trigger_event))
    return True

async def _run_and_deliver(self, job: ProactiveJob, trigger_event: EventEnvelope | None = None) -> None:
    session_id, result = await self._executor.execute_job(job, trigger_event)
    if self._delivery and job.state.last_status == "ok" and result:
        source_session_id = trigger_event.session_id if trigger_event else None
        await self._delivery.deliver(job, session_id, result, source_session_id=source_session_id)
```

- [ ] **Step 4: 修改 Executor.execute_job 签名**

```python
# sensenova_claw/kernel/proactive/executor.py
async def execute_job(self, job: ProactiveJob, trigger_event: EventEnvelope | None = None) -> tuple[str, str | None]:
    # ... 现有逻辑不变，trigger_event 传给 _do_execute
    ...
    return await self._do_execute(job, trigger_event)

async def _do_execute(self, job: ProactiveJob, trigger_event: EventEnvelope | None = None) -> tuple[str, str | None]:
    # 现有逻辑不变（独立会话模式），trigger_event 暂时不使用
    # Task 5 会增加注入模式
    ...
```

- [ ] **Step 5: 运行全部 proactive 单元测试确认无回归**

Run: `python3 -m pytest tests/unit/kernel/proactive/ -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add sensenova_claw/kernel/proactive/scheduler.py sensenova_claw/kernel/proactive/runtime.py sensenova_claw/kernel/proactive/executor.py tests/unit/kernel/proactive/test_runtime.py
git commit -m "feat(proactive): pass trigger_event through scheduler→runtime→executor chain"
```

---

## Task 5: Executor 注入模式 — 在源会话中生成推荐

**Files:**
- Modify: `sensenova_claw/kernel/proactive/executor.py:80-156` (_do_execute)
- Modify: `sensenova_claw/kernel/proactive/executor.py:231-273` (_wait_for_completion)
- Create: `tests/unit/kernel/proactive/test_executor.py`

- [ ] **Step 1: 写失败测试 — 注入模式使用 send_user_input**

```python
# tests/unit/kernel/proactive/test_executor.py
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

@pytest.mark.asyncio
async def test_inject_mode_calls_send_user_input():
    """当 trigger_event 存在时，executor 应调用 send_user_input 而非 spawn_agent_session。"""
    bus = MagicMock()
    bus.publish = AsyncMock()
    bus.subscribe = MagicMock()
    repo = MagicMock()
    repo.create_proactive_run = AsyncMock()
    repo.update_proactive_run = AsyncMock()
    repo.update_proactive_job = AsyncMock()

    agent_runtime = MagicMock()
    agent_runtime.spawn_agent_session = AsyncMock()
    agent_runtime.send_user_input = AsyncMock(return_value="turn_rec_123")

    executor = ProactiveExecutor(bus=bus, repo=repo, agent_runtime=agent_runtime, memory_manager=None)

    trigger_event = EventEnvelope(
        type="agent.step_completed",
        session_id="user-session-1",
        payload={"step_type": "final"},
    )

    job = _make_recommendation_job()

    # Mock _wait_for_completion 返回推荐 JSON
    with patch.object(executor, '_wait_for_completion', new_callable=AsyncMock) as mock_wait:
        mock_wait.return_value = '{"recommendations": [{"id": "1", "title": "test", "prompt": "do test", "category": "action"}]}'
        session_id, result = await executor.execute_job(job, trigger_event)

    # 应该调用 send_user_input 而非 spawn_agent_session
    agent_runtime.send_user_input.assert_called_once()
    agent_runtime.spawn_agent_session.assert_not_called()
    # session_id 应该是源会话
    assert session_id == "user-session-1"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/kernel/proactive/test_executor.py::test_inject_mode_calls_send_user_input -v`
Expected: FAIL — executor 还没有注入模式逻辑

- [ ] **Step 3: 实现 _do_execute 注入模式分支**

在 `_do_execute` 方法开头增加注入模式判断：

```python
async def _do_execute(self, job: ProactiveJob, trigger_event: EventEnvelope | None = None) -> tuple[str, str | None]:
    # 注入模式：在源会话中插入推荐请求
    if trigger_event and job.delivery.recommendation_type:
        return await self._do_execute_inject(job, trigger_event)

    # 独立会话模式（现有逻辑不变）
    session_id = f"proactive_{job.id}_{uuid.uuid4().hex[:8]}"
    ...
```

- [ ] **Step 4: 实现 _do_execute_inject 方法**

```python
async def _do_execute_inject(self, job: ProactiveJob, trigger_event: EventEnvelope) -> tuple[str, str | None]:
    """注入模式：在源会话中插入 user 消息生成推荐。"""
    source_session_id = trigger_event.session_id
    run_id = f"pr_{uuid.uuid4().hex[:12]}"
    start_ms = int(time.time() * 1000)
    self._running_jobs.add(job.id)
    job.state.last_triggered_at_ms = start_ms
    job.state.last_status = "running"

    await self._repo.create_proactive_run({
        "id": run_id, "job_id": job.id,
        "session_id": source_session_id,
        "status": "running", "triggered_by": "event",
        "started_at_ms": start_ms,
    })

    try:
        turn_id = await self._agent_runtime.send_user_input(
            session_id=source_session_id,
            user_input=job.task.prompt,
            extra_payload={"meta": {"source": "recommendation"}},
        )

        timeout_ms = job.safety.max_duration_ms
        result_text = await self._wait_for_completion_by_turn(
            source_session_id, turn_id, timeout_ms,
        )

        if result_text is None:
            end_ms = int(time.time() * 1000)
            await self._handle_failure(
                job, run_id, source_session_id,
                f"执行超时（{timeout_ms}ms）", end_ms, status="timeout",
            )
            return (source_session_id, None)

        # 成功
        end_ms = int(time.time() * 1000)
        job.state.last_status = "ok"
        job.state.last_completed_at_ms = end_ms
        job.state.consecutive_errors = 0
        job.state.total_runs += 1
        await self._repo.update_proactive_run(run_id, {
            "status": "ok", "ended_at_ms": end_ms, "result_text": result_text[:2000],
        })
        await self._persist_job_state(job)
        return (source_session_id, result_text)

    except Exception as e:
        end_ms = int(time.time() * 1000)
        await self._handle_failure(job, run_id, source_session_id, str(e), end_ms)
        return (source_session_id, None)
    finally:
        self._running_jobs.discard(job.id)
```

- [ ] **Step 5: 实现 _wait_for_completion_by_turn 方法**

```python
async def _wait_for_completion_by_turn(
    self, session_id: str, turn_id: str, timeout_ms: float,
) -> str | None:
    """等待指定 turn 的 agent.step_completed 事件。"""
    queue: asyncio.Queue[EventEnvelope] = asyncio.Queue()
    sub_id = await self._bus.subscribe_queue(queue)
    heartbeat_timeout = timeout_ms / 3
    last_activity = time.time() * 1000

    try:
        while True:
            remaining = (timeout_ms - (time.time() * 1000 - last_activity * 1000 / heartbeat_timeout)) / 1000
            try:
                event = await asyncio.wait_for(queue.get(), timeout=heartbeat_timeout / 1000)
            except asyncio.TimeoutError:
                if (time.time() * 1000 - last_activity) > timeout_ms:
                    return None
                continue

            if event.session_id != session_id:
                continue
            last_activity = time.time() * 1000

            if event.type == AGENT_STEP_COMPLETED and event.turn_id == turn_id:
                return event.payload.get("result", {}).get("content", "")
    finally:
        await self._bus.unsubscribe_queue(sub_id)
```

注意：实际实现时参考现有 `_wait_for_completion` 的 subscribe 模式（可能是 `async for` 而非 queue），保持一致。

- [ ] **Step 6: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/kernel/proactive/test_executor.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add sensenova_claw/kernel/proactive/executor.py tests/unit/kernel/proactive/test_executor.py
git commit -m "feat(proactive): add inject mode to executor for in-session recommendation"
```

---

## Task 6: JSON 推荐解析与 Delivery 扩展

**Files:**
- Modify: `sensenova_claw/kernel/proactive/delivery.py:22-47` (deliver 方法)
- Modify: `sensenova_claw/kernel/proactive/runtime.py:171-174` (_run_and_deliver)
- Test: `tests/unit/kernel/proactive/test_delivery.py`

- [ ] **Step 1: 写失败测试 — deliver 携带 items 和 source_session_id**

```python
# tests/unit/kernel/proactive/test_delivery.py — 新增

@pytest.mark.asyncio
async def test_deliver_with_recommendation_items(mock_bus, mock_notification):
    delivery = ProactiveDelivery(bus=mock_bus, notification_service=mock_notification)
    job = _make_job(["web"])
    job.delivery.recommendation_type = "turn_end"

    items = [{"id": "1", "title": "test", "prompt": "do test", "category": "action"}]
    await delivery.deliver(
        job, "session-1", "raw result",
        source_session_id="user-session-1",
        items=items,
    )

    event = mock_bus.publish.call_args[0][0]
    assert event.payload["source_session_id"] == "user-session-1"
    assert event.payload["recommendation_type"] == "turn_end"
    assert event.payload["items"] == items
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/kernel/proactive/test_delivery.py::test_deliver_with_recommendation_items -v`
Expected: FAIL — `deliver()` 不接受 `source_session_id` 和 `items` 参数

- [ ] **Step 3: 扩展 deliver() 方法签名和 payload**

```python
# sensenova_claw/kernel/proactive/delivery.py
async def deliver(
    self, job: ProactiveJob, session_id: str, result: str,
    *,
    source_session_id: str | None = None,
    items: list[dict] | None = None,
):
    """投递 proactive 执行结果：发布事件 + 发送通知。"""
    payload = {
        "job_id": job.id,
        "job_name": job.name,
        "result": result,
        "session_id": session_id,
    }
    if source_session_id:
        payload["source_session_id"] = source_session_id
    if job.delivery.recommendation_type:
        payload["recommendation_type"] = job.delivery.recommendation_type
    if items:
        payload["items"] = items

    await self._bus.publish(EventEnvelope(
        type=PROACTIVE_RESULT,
        session_id=session_id,
        agent_id=job.agent_id,
        payload=payload,
        source="proactive",
    ))
    # ... 通知逻辑不变
```

- [ ] **Step 4: 实现 _run_and_deliver 中的 JSON 解析**

```python
# sensenova_claw/kernel/proactive/runtime.py — _run_and_deliver
import json, re

async def _run_and_deliver(self, job: ProactiveJob, trigger_event: EventEnvelope | None = None) -> None:
    session_id, result = await self._executor.execute_job(job, trigger_event)
    if not (self._delivery and job.state.last_status == "ok" and result):
        return

    source_session_id = trigger_event.session_id if trigger_event else None
    items = None

    # 推荐类型 job：解析 JSON
    if job.delivery.recommendation_type:
        items = self._parse_recommendation_json(result)
        if items is None:
            logger.warning("推荐 JSON 解析失败，跳过投递: job=%s", job.id)
            return

    await self._delivery.deliver(
        job, session_id, result,
        source_session_id=source_session_id,
        items=items,
    )

@staticmethod
def _parse_recommendation_json(text: str) -> list[dict] | None:
    """从 LLM 回复中提取推荐 JSON。支持 markdown code block 包裹。"""
    # 尝试提取 code block 中的 JSON
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    json_str = match.group(1) if match else text

    try:
        data = json.loads(json_str)
        recs = data.get("recommendations")
        if isinstance(recs, list) and len(recs) > 0:
            return recs
        return None
    except (json.JSONDecodeError, AttributeError):
        return None
```

- [ ] **Step 5: 写 JSON 解析测试**

```python
# tests/unit/kernel/proactive/test_runtime.py — 新增
from sensenova_claw.kernel.proactive.runtime import ProactiveRuntime

class TestParseRecommendationJson:
    def test_plain_json(self):
        text = '{"recommendations": [{"id": "1", "title": "t", "prompt": "p", "category": "action"}]}'
        result = ProactiveRuntime._parse_recommendation_json(text)
        assert len(result) == 1
        assert result[0]["title"] == "t"

    def test_code_block_json(self):
        text = '```json\n{"recommendations": [{"id": "1", "title": "t", "prompt": "p"}]}\n```'
        result = ProactiveRuntime._parse_recommendation_json(text)
        assert len(result) == 1

    def test_invalid_json_returns_none(self):
        assert ProactiveRuntime._parse_recommendation_json("not json") is None

    def test_missing_recommendations_key(self):
        assert ProactiveRuntime._parse_recommendation_json('{"items": []}') is None

    def test_empty_recommendations(self):
        assert ProactiveRuntime._parse_recommendation_json('{"recommendations": []}') is None
```

- [ ] **Step 6: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/kernel/proactive/test_delivery.py tests/unit/kernel/proactive/test_runtime.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add sensenova_claw/kernel/proactive/delivery.py sensenova_claw/kernel/proactive/runtime.py tests/unit/kernel/proactive/test_delivery.py tests/unit/kernel/proactive/test_runtime.py
git commit -m "feat(proactive): extend delivery with recommendation items and JSON parsing"
```

---

## Task 7: AgentWorker 透传 meta.source 到 step_completed payload

**Files:**
- Modify: `sensenova_claw/kernel/runtime/workers/agent_worker.py:525-537` (step_completed 发布)

- [ ] **Step 1: 确认 send_user_input 的 extra_payload 如何传递 meta**

检查 `agent_runtime.send_user_input` 的 `extra_payload` 是否会被 AgentWorker 读取。如果 `extra_payload` 中的 `meta` 字段会被存入 turn 或 session 的 meta，则 AgentWorker 可以在发布 `step_completed` 时读取。

如果不是，需要在 `USER_INPUT` 事件的 payload 中增加 `meta` 字段，AgentWorker 在 `_handle_user_input` 中提取并存储到 TurnState。

- [ ] **Step 2: 修改 AgentWorker 发布 step_completed 时透传 source**

```python
# sensenova_claw/kernel/runtime/workers/agent_worker.py
# 在发布 AGENT_STEP_COMPLETED 的 payload 中，检查 turn 的 meta 是否有 source 字段
payload = {
    "step_type": "final",
    "result": {"content": content},
    "next_action": "end",
}
# 如果 turn 有 meta.source，透传到 payload
turn_meta = event.payload.get("meta") or {}
if turn_meta.get("source"):
    payload["source"] = turn_meta["source"]
```

具体实现取决于 `extra_payload` 在 `USER_INPUT` 事件中的传递方式。实现时需要追踪 `extra_payload.meta` 从 `send_user_input` → `USER_INPUT` 事件 → `_handle_user_input` → TurnState → `step_completed` payload 的完整链路。

- [ ] **Step 3: 运行全部 proactive 测试确认无回归**

Run: `python3 -m pytest tests/unit/kernel/proactive/ -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add sensenova_claw/kernel/runtime/workers/agent_worker.py
git commit -m "feat(agent-worker): propagate turn meta.source to step_completed payload"
```

---

## Task 8: 内置 Job 注册与配置

**Files:**
- Modify: `sensenova_claw/kernel/proactive/runtime.py:83-91,178-194` (start、_load_all_jobs)
- Test: `tests/unit/kernel/proactive/test_runtime.py`

- [ ] **Step 1: 写失败测试 — 内置 job 自动注册**

```python
# tests/unit/kernel/proactive/test_runtime.py — 新增

@pytest.mark.asyncio
async def test_builtin_recommendation_job_registered():
    """ProactiveRuntime 启动后应包含内置推荐 job。"""
    # 构造 runtime（使用 mock 依赖）
    # 调用 start()
    # 验证 _jobs 中包含 "builtin-turn-end-recommendation"
    pass  # 实现时根据现有 fixture 补全
```

- [ ] **Step 2: 实现内置 job 注册**

在 `_load_all_jobs` 末尾增加内置 job 注册：

```python
# sensenova_claw/kernel/proactive/runtime.py — _load_all_jobs 末尾
async def _load_all_jobs(self) -> None:
    # ... 现有逻辑 ...

    # 注册内置推荐 job（如果配置启用）
    self._register_builtin_recommendation_job()

def _register_builtin_recommendation_job(self) -> None:
    """注册内置的 turn-end 推荐 job。"""
    from sensenova_claw.platform.config.config import config as _cfg
    rec_cfg = _cfg.get("proactive.turn_end_recommendation", {})
    if not rec_cfg.get("enabled", True):
        return

    job_id = "builtin-turn-end-recommendation"
    if job_id in self._jobs:
        return  # 已存在（可能从 DB 加载）

    job = ProactiveJob(
        id=job_id,
        name="会话推荐",
        agent_id="proactive-agent",
        enabled=True,
        trigger=EventTrigger(
            event_type="agent.step_completed",
            debounce_ms=rec_cfg.get("debounce_ms", 5000),
            exclude_payload={"source": "recommendation"},
        ),
        task=ProactiveTask(
            prompt="根据以上完整对话上下文，生成3-5条用户接下来可能想做的事。每条包含title和prompt字段，输出JSON格式：{\"recommendations\": [{\"id\": \"uuid\", \"title\": \"标题\", \"prompt\": \"完整提示词\", \"category\": \"research|action|follow-up\"}]}",
        ),
        delivery=DeliveryConfig(
            channels=["web"],
            recommendation_type="turn_end",
        ),
        safety=SafetyConfig(
            max_tool_calls=rec_cfg.get("max_tool_calls", 5),
            max_llm_calls=rec_cfg.get("max_llm_calls", 3),
            max_duration_ms=rec_cfg.get("max_duration_ms", 30000),
        ),
        state=JobState(),
        source="builtin",
    )
    self._jobs[job_id] = job
    logger.info("已注册内置推荐 job: %s", job_id)
```

- [ ] **Step 3: 更新 _parse_job_config 解析 exclude_payload**

```python
# sensenova_claw/kernel/proactive/runtime.py — _parse_job_config 中 event 分支
elif trigger_kind == "event":
    trigger = EventTrigger(
        event_type=trigger_cfg.get("event_type", ""),
        filter=trigger_cfg.get("filter"),
        debounce_ms=trigger_cfg.get("debounce_ms", 5000),
        exclude_payload=trigger_cfg.get("exclude_payload"),  # 新增
    )

# delivery 解析中增加 recommendation_type
delivery = DeliveryConfig(
    channels=delivery_cfg.get("channels", []),
    feishu_target=delivery_cfg.get("feishu_target"),
    summary_prompt=delivery_cfg.get("summary_prompt"),
    recommendation_type=delivery_cfg.get("recommendation_type"),  # 新增
)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/kernel/proactive/ -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add sensenova_claw/kernel/proactive/runtime.py tests/unit/kernel/proactive/test_runtime.py
git commit -m "feat(proactive): register builtin turn-end recommendation job on startup"
```

---

## Task 9: 前端 — ChatSessionContext 推荐 state 和 prefillInput

**Files:**
- Modify: `sensenova_claw/app/web/contexts/ChatSessionContext.tsx:100-107,770-800` (ProactiveResultItem、handleWsMessage)

- [ ] **Step 1: 扩展 ProactiveResultItem 接口**

```typescript
// ChatSessionContext.tsx — ProactiveResultItem 接口
export interface ProactiveResultItem {
  jobId: string;
  jobName: string;
  sessionId: string;
  result: string;
  receivedAt: number;
  // 新增
  sourceSessionId?: string;
  recommendationType?: string;
  items?: Array<{
    id: string;
    title: string;
    prompt: string;
    category?: string;
  }>;
}
```

- [ ] **Step 2: 新增 pendingInput state 和 prefillInput 方法**

```typescript
// ChatSessionContext.tsx — state 声明区域
const [pendingInput, setPendingInput] = useState<string>('');

// context value 中暴露
const prefillInput = useCallback((text: string) => {
  setPendingInput(text);
}, []);

// 在 context value 对象中添加:
// pendingInput, prefillInput, setPendingInput
```

- [ ] **Step 3: 修改 proactive_result 事件处理**

```typescript
// ChatSessionContext.tsx — handleWsMessage 中 proactive_result case
case 'proactive_result': {
  const jobId = String(payload.job_id || '');
  const jobName = String(payload.job_name || '');
  const resultText = String(payload.result || '');
  const sourceSessionId = payload.source_session_id ? String(payload.source_session_id) : undefined;
  const recommendationType = payload.recommendation_type ? String(payload.recommendation_type) : undefined;
  const items = Array.isArray(payload.items) ? payload.items : undefined;

  const newItem: ProactiveResultItem = {
    jobId, jobName, result: resultText,
    sessionId: resultSessionId,
    receivedAt: Date.now(),
    sourceSessionId,
    recommendationType,
    items,
  };

  setProactiveResults(prev => {
    const deduped = prev.filter(r => !(r.jobId === jobId && r.sessionId === resultSessionId));
    return [newItem, ...deduped].slice(0, 50);
  });

  // ... 现有 notification 逻辑不变
}
```

- [ ] **Step 4: Commit**

```bash
git add sensenova_claw/app/web/contexts/ChatSessionContext.tsx
git commit -m "feat(web): add recommendation fields to ProactiveResultItem and prefillInput"
```

---

## Task 10: 前端 — useDashboardData 推荐聚合

**Files:**
- Modify: `sensenova_claw/app/web/hooks/useDashboardData.ts:284-316`

- [ ] **Step 1: 新增 RecommendationGroup 类型和聚合逻辑**

```typescript
// useDashboardData.ts — 新增类型
export interface RecommendationItem {
  id: string;
  title: string;
  prompt: string;
  category?: string;
  sourceSessionId: string;
  receivedAt: number;
}

export interface RecommendationGroup {
  sourceSessionId: string;
  items: RecommendationItem[];
  receivedAt: number;
}
```

- [ ] **Step 2: 实现推荐聚合函数**

```typescript
// useDashboardData.ts — 新增函数
function aggregateRecommendations(proactiveResults: ProactiveResultItem[]): RecommendationGroup[] {
  const now = Date.now();
  const DAY_MS = 24 * 60 * 60 * 1000;

  // 只取 turn_end 类型且未过期的
  const recResults = proactiveResults.filter(
    r => r.recommendationType === 'turn_end' && r.items?.length && (now - r.receivedAt) < DAY_MS
  );

  // 按 sourceSessionId 分组，同 session 只保留最新
  const bySession = new Map<string, ProactiveResultItem>();
  for (const r of recResults) {
    const sid = r.sourceSessionId || r.sessionId;
    const existing = bySession.get(sid);
    if (!existing || r.receivedAt > existing.receivedAt) {
      bySession.set(sid, r);
    }
  }

  // 转为 RecommendationGroup，按时间倒序，最多 3 个 session
  return Array.from(bySession.entries())
    .sort((a, b) => b[1].receivedAt - a[1].receivedAt)
    .slice(0, 3)
    .map(([sid, r]) => ({
      sourceSessionId: sid,
      receivedAt: r.receivedAt,
      items: (r.items || []).slice(0, 5).map(item => ({
        ...item,
        sourceSessionId: sid,
        receivedAt: r.receivedAt,
      })),
    }));
}
```

- [ ] **Step 3: 在 useDashboardData 返回值中暴露 recommendations**

```typescript
// useDashboardData.ts — 在 hook 返回值中增加
const recommendations = useMemo(
  () => aggregateRecommendations(proactiveResults || []),
  [proactiveResults],
);

return {
  // ... 现有字段
  recommendations,
};
```

- [ ] **Step 4: Commit**

```bash
git add sensenova_claw/app/web/hooks/useDashboardData.ts
git commit -m "feat(web): aggregate turn-end recommendations in useDashboardData"
```

---

## Task 11: 前端 — ProactiveAgentPanel 推荐卡片渲染与交互

**Files:**
- Modify: `sensenova_claw/app/web/components/dashboard/ProactiveAgentPanel.tsx`
- Modify: `sensenova_claw/app/web/components/dashboard/Dashboard.tsx`

- [ ] **Step 1: 扩展 ProactiveAgentPanel props**

```typescript
// ProactiveAgentPanel.tsx
interface ProactiveAgentPanelProps {
  items: RecentOutput[];
  onItemClick?: (id: string) => void;
  // 新增
  recommendations?: RecommendationGroup[];
  onRecommendationClick?: (sourceSessionId: string, prompt: string) => void;
}
```

- [ ] **Step 2: 实现推荐卡片组件**

```typescript
// ProactiveAgentPanel.tsx — 新增 RecommendationCard 组件
const CATEGORY_STYLES: Record<string, { icon: string; color: string }> = {
  research: { icon: '🔍', color: 'sky' },
  action: { icon: '⚡', color: 'emerald' },
  'follow-up': { icon: '💬', color: 'amber' },
};

function RecommendationCard({
  item, onClick,
}: {
  item: RecommendationItem;
  onClick: () => void;
}) {
  const style = CATEGORY_STYLES[item.category || ''] || { icon: '💡', color: 'neutral' };
  return (
    <button
      onClick={onClick}
      className="w-full text-left p-2 rounded-lg hover:bg-white/10 transition-colors"
    >
      <span className="text-sm">{style.icon} {item.title}</span>
    </button>
  );
}
```

- [ ] **Step 3: 在 ProactiveAgentPanel 中渲染推荐区域**

在现有 proactive 推送列表上方或下方增加推荐区域：

```typescript
// ProactiveAgentPanel.tsx — 在 return 中增加推荐区域
{recommendations && recommendations.length > 0 && (
  <div className="mb-3">
    <div className="text-xs text-white/50 mb-1">推荐操作</div>
    {recommendations.map(group => (
      <div key={group.sourceSessionId} className="mb-2">
        {group.items.map(item => (
          <RecommendationCard
            key={item.id}
            item={item}
            onClick={() => onRecommendationClick?.(group.sourceSessionId, item.prompt)}
          />
        ))}
      </div>
    ))}
  </div>
)}
```

- [ ] **Step 4: 修改 Dashboard 传递推荐数据和回调**

```typescript
// Dashboard.tsx — handleOutputClick 附近新增
const handleRecommendationClick = useCallback(async (sourceSessionId: string, prompt: string) => {
  await switchSession(sourceSessionId);
  prefillInput(prompt);
}, [switchSession, prefillInput]);

// ProactiveAgentPanel 调用处增加 props
<ProactiveAgentPanel
  items={proactiveOutputs}
  onItemClick={handleOutputClick}
  recommendations={recommendations}
  onRecommendationClick={handleRecommendationClick}
/>
```

- [ ] **Step 5: 在 ChatInput 中监听 pendingInput**

```typescript
// ChatInput.tsx — 新增 useEffect 监听 pendingInput
const { pendingInput, setPendingInput } = useChatSession();

useEffect(() => {
  if (pendingInput) {
    setInputValue(pendingInput);
    setPendingInput('');
    setTimeout(() => {
      textareaRef.current?.focus();
    });
  }
}, [pendingInput, setPendingInput]);
```

- [ ] **Step 6: Commit**

```bash
git add sensenova_claw/app/web/components/dashboard/ProactiveAgentPanel.tsx sensenova_claw/app/web/components/dashboard/Dashboard.tsx sensenova_claw/app/web/components/chat/ChatInput.tsx
git commit -m "feat(web): render recommendation cards with click-to-fill interaction"
```

---

## Task 12: 隐藏推荐 turn 消息 & 最终集成测试

**Files:**
- Modify: `sensenova_claw/app/web/contexts/ChatSessionContext.tsx` (消息过滤)

- [ ] **Step 1: 前端过滤 hidden 消息**

在 ChatSessionContext 加载会话消息时，过滤掉 `meta.source === "recommendation"` 的消息。具体实现取决于消息结构中 meta 的传递方式。

如果后端 `save_message` 不支持 meta 字段，需要在 messages 表增加 `meta TEXT` 列，或者在 turn 级别标记。实现时需要追踪完整链路。

- [ ] **Step 2: 手动集成测试**

1. 启动后端 + 前端：`sensenova-claw run`
2. 在 Dashboard 确认 ProactiveAgentPanel 可见
3. 发送一条消息，等待 turn 完成
4. 观察 5 秒后看板是否出现推荐卡片
5. 点击推荐卡片，确认跳转到对应会话且输入框已填入 prompt
6. 确认对话流中不显示推荐 turn 的消息

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat(web): hide recommendation turn messages from chat flow"
```

---
