# Delegation 心跳续期超时机制 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 send_message 的超时机制从固定总超时改为心跳无活动超时，并为 delegation session 添加工具/LLM 调用轮次限制。

**Architecture:** coordinator 在现有 `_event_loop` 中监听子 Agent 的关键事件作为心跳信号，收到心跳后重置超时计时器。`_timeout_after` 改为循环检查无活动时间。agent_worker 新增 `_is_autonomous_session()` 方法，将轮次限制扩展到 delegation session。

**Tech Stack:** Python 3.12, asyncio, pytest

**Spec:** `docs/superpowers/specs/2026-03-24-delegation-heartbeat-timeout-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `sensenova_claw/platform/config/config.py` | Modify:289-297 | 新增 delegation 轮次限制默认配置 |
| `sensenova_claw/kernel/runtime/workers/agent_worker.py` | Modify:132-134, 354, 564, 577 | 新增 `_is_autonomous_session()`，替换调用点 |
| `sensenova_claw/kernel/runtime/agent_message_coordinator.py` | Modify:11-18, 46-50, 139-151, 229-246, 451-477, 487-537 | 心跳字段、事件监听、超时逻辑、retry 续期、meta 传入 |
| `sensenova_claw/capabilities/tools/send_message_tool.py` | Modify:64 | 更新参数描述 |
| `tests/unit/test_agent_message_coordinator.py` | Modify + Add | 新增 5 个心跳相关测试 |
| `tests/unit/test_agent_worker.py` | Add (if not exist) | 新增 2 个 delegation 轮次限制测试 |

---

### Task 1: 新增 delegation 轮次限制配置

**Files:**
- Modify: `sensenova_claw/platform/config/config.py:289-297`

- [ ] **Step 1: 在 DEFAULT_CONFIG 的 delegation 中新增 max_tool_calls 和 max_llm_calls**

```python
# sensenova_claw/platform/config/config.py:289-297
# 将：
    "delegation": {
        "max_depth": 3,
        "default_timeout": 300,
        "retry": {
            "max_retries": 0,
            "backoff_seconds": [0, 1, 3],
        },
        "enabled": True,
    },
# 改为：
    "delegation": {
        "max_depth": 3,
        "default_timeout": 300,
        "max_tool_calls": 30,
        "max_llm_calls": 15,
        "retry": {
            "max_retries": 0,
            "backoff_seconds": [0, 1, 3],
        },
        "enabled": True,
    },
```

- [ ] **Step 2: 验证配置加载**

Run: `python3 -c "from sensenova_claw.platform.config.config import DEFAULT_CONFIG; d=DEFAULT_CONFIG['delegation']; assert d['max_tool_calls']==30; assert d['max_llm_calls']==15; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add sensenova_claw/platform/config/config.py
git commit -m "feat(delegation): 新增 max_tool_calls/max_llm_calls 默认配置"
```

---

### Task 2: agent_worker 扩展轮次限制到 delegation session

**Files:**
- Modify: `sensenova_claw/kernel/runtime/workers/agent_worker.py:132-134, 354, 564, 577`
- Test: `tests/unit/test_agent_worker_delegation_limits.py`

- [ ] **Step 1: 写失败测试 — delegation session 触发 max_tool_calls 限制**

创建 `tests/unit/test_agent_worker_delegation_limits.py`：

```python
"""测试 delegation session 的轮次限制。"""
from __future__ import annotations

import pytest

from sensenova_claw.kernel.runtime.workers.agent_worker import AgentSessionWorker


pytestmark = pytest.mark.asyncio


class TestDelegationSessionLimits:
    def test_is_autonomous_session_with_delegation_meta(self):
        """delegation session（含 message_trace_id）应被识别为自治会话"""
        worker = AgentSessionWorker.__new__(AgentSessionWorker)
        worker._session_meta = {"message_trace_id": "rec_123"}
        assert worker._is_autonomous_session() is True

    def test_is_autonomous_session_with_proactive_meta(self):
        """proactive session 仍应被识别为自治会话"""
        worker = AgentSessionWorker.__new__(AgentSessionWorker)
        worker._session_meta = {"proactive_job_id": "job_1"}
        assert worker._is_autonomous_session() is True

    def test_is_autonomous_session_with_normal_session(self):
        """普通用户会话不应被识别为自治会话"""
        worker = AgentSessionWorker.__new__(AgentSessionWorker)
        worker._session_meta = {"agent_id": "default"}
        assert worker._is_autonomous_session() is False

    def test_is_autonomous_session_with_none_meta(self):
        """session_meta 为 None 时不应被识别为自治会话"""
        worker = AgentSessionWorker.__new__(AgentSessionWorker)
        worker._session_meta = None
        assert worker._is_autonomous_session() is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/test_agent_worker_delegation_limits.py -v`
Expected: FAIL — `_is_autonomous_session` 不存在

- [ ] **Step 3: 实现 _is_autonomous_session 并替换调用点**

在 `sensenova_claw/kernel/runtime/workers/agent_worker.py` 中：

```python
# 在 _is_proactive_session 方法后新增（约 line 135）：
    def _is_autonomous_session(self) -> bool:
        """判断当前会话是否为自治会话（proactive 或 delegation）"""
        if not self._session_meta:
            return False
        return bool(
            self._session_meta.get("proactive_job_id")
            or self._session_meta.get("message_trace_id")
        )
```

然后将 4 处 `self._is_proactive_session()` 替换为 `self._is_autonomous_session()`：
- line 354: 第一个 LLM 调用限制检查
- line 564: 工具调用限制检查
- line 577: 第二个 LLM 调用限制检查

同时更新注释，将"仅 proactive 会话"改为"仅自治会话（proactive/delegation）"。

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/test_agent_worker_delegation_limits.py -v`
Expected: 4 passed

- [ ] **Step 5: 运行现有单元测试确认无回归**

Run: `python3 -m pytest tests/unit/ -q --timeout=30`
Expected: 全部通过

- [ ] **Step 6: Commit**

```bash
git add sensenova_claw/kernel/runtime/workers/agent_worker.py tests/unit/test_agent_worker_delegation_limits.py
git commit -m "feat(agent_worker): 扩展轮次限制到 delegation session"
```

---

### Task 3: coordinator 传入轮次限制 meta

**Files:**
- Modify: `sensenova_claw/kernel/runtime/agent_message_coordinator.py:229-246`

- [ ] **Step 1: 在 _handle_message_requested 的 spawn meta 中加入轮次限制**

在 `agent_message_coordinator.py` 的 `_handle_message_requested` 方法中，找到 `meta = {` 块（约 line 230），在 `"message_trace_id": record.id,` 之后新增：

```python
                    "max_tool_calls": int(
                        event.payload.get("max_tool_calls", 0)
                    ) or None,
                    "max_llm_calls": int(
                        event.payload.get("max_llm_calls", 0)
                    ) or None,
```

注意：这些值从 event payload 中读取，由 send_message_tool 从配置中传入。如果 payload 中没有，则不设限（None），由 agent_worker 的 `_is_autonomous_session` + `session_meta.get("max_tool_calls")` 自然处理为不限制。

- [ ] **Step 2: 在 send_message_tool 中传入轮次限制到 event payload**

在 `sensenova_claw/capabilities/tools/send_message_tool.py` 中：

**2a. 构造函数新增参数（与 `timeout` 和 `default_max_retries` 同级）：**

```python
    def __init__(
        self,
        agent_registry: AgentRegistry,
        bus: PublicEventBus,
        repo: Repository,
        coordinator: AgentMessageCoordinator,
        timeout: float = 300,
        default_max_retries: int = 0,
        max_tool_calls: int = 30,       # 新增
        max_llm_calls: int = 15,        # 新增
    ):
        # ... 现有字段 ...
        self._max_tool_calls = max_tool_calls
        self._max_llm_calls = max_llm_calls
```

**2b. 在 payload 中传入（约 line 268-269，`"max_retries": max_retries,` 之后）：**

```python
                    "max_tool_calls": self._max_tool_calls,
                    "max_llm_calls": self._max_llm_calls,
```

**2c. 在 gateway/main.py 中传入配置值（约 line 261-262）：**

```python
        send_message_tool = SendMessageTool(
            agent_registry=agent_registry,
            bus=bus,
            repo=repo,
            coordinator=agent_message_coordinator,
            timeout=float(config.get("delegation.default_timeout", 300)),
            default_max_retries=int(config.get("delegation.retry.max_retries", 0)),
            max_tool_calls=int(config.get("delegation.max_tool_calls", 30)),
            max_llm_calls=int(config.get("delegation.max_llm_calls", 15)),
        )
```

- [ ] **Step 3: 同时更新 timeout_seconds 参数描述**

在 `send_message_tool.py` line 64，将：
```python
                "description": "可选。整条消息链路的总超时秒数，默认使用系统配置。",
```
改为：
```python
                "description": "可选。无活动超时秒数（子 Agent 有活动时自动续期），默认使用系统配置。",
```

- [ ] **Step 4: 验证 meta 传递**

Run: `python3 -m pytest tests/unit/test_agent_message_coordinator.py::TestAgentMessageCoordinator::test_requested_creates_record_and_spawns_child -v`
Expected: PASS（现有测试不检查 meta 中的新字段，不会失败）

- [ ] **Step 5: Commit**

```bash
git add sensenova_claw/kernel/runtime/agent_message_coordinator.py sensenova_claw/capabilities/tools/send_message_tool.py sensenova_claw/app/gateway/main.py
git commit -m "feat(coordinator): spawn delegation session 时传入轮次限制 meta，更新超时参数描述"
```

---

### Task 4: coordinator 心跳续期超时机制

**Files:**
- Modify: `sensenova_claw/kernel/runtime/agent_message_coordinator.py:11-18, 46-50, 139-151, 451-477`
- Test: `tests/unit/test_agent_message_coordinator.py`

- [ ] **Step 1: 写失败测试 — 心跳续期不超时**

在 `tests/unit/test_agent_message_coordinator.py` 中新增：

```python
from sensenova_claw.kernel.events.types import (
    AGENT_MESSAGE_REQUESTED,
    AGENT_STEP_COMPLETED,
    ERROR_RAISED,
    LLM_CALL_REQUESTED,
    TOOL_CALL_COMPLETED,
    USER_TURN_CANCEL_REQUESTED,
)

# ... 在 TestAgentMessageCoordinator 类中新增：

    async def test_heartbeat_resets_timeout(self, test_repo):
        """子 Agent 有心跳时不应超时"""
        bus = PublicEventBus()
        runtime = _FakeAgentRuntime()
        coordinator = AgentMessageCoordinator(
            bus=bus, repo=test_repo, agent_runtime=runtime,
        )
        await coordinator.start()
        waiter = coordinator.register_sync_waiter("record_hb")

        await bus.publish(EventEnvelope(
            type=AGENT_MESSAGE_REQUESTED,
            session_id="parent",
            trace_id="record_hb",
            payload={
                "record_id": "record_hb",
                "target_id": "helper",
                "message": "心跳任务",
                "mode": "sync",
                "depth": 1,
                "send_chain": ["default"],
                "parent_session_id": "parent",
                "timeout_seconds": 0.3,
                "max_retries": 0,
            },
        ))
        await asyncio.sleep(0.1)  # 让 coordinator 处理事件

        record = await test_repo.get_message_record("record_hb")
        assert record is not None
        child_sid = record.child_session_id

        # 在 timeout 到期前持续发心跳（每 0.15s 一次，共 3 次 = 0.45s > timeout 0.3s）
        for _ in range(3):
            await asyncio.sleep(0.15)
            await bus.publish(EventEnvelope(
                type=LLM_CALL_REQUESTED,
                session_id=child_sid,
                payload={},
            ))

        # 再等一小段确认没超时
        await asyncio.sleep(0.1)
        record = await test_repo.get_message_record("record_hb")
        assert record is not None
        assert record.status == "running", f"Expected running but got {record.status}"

        # 手动完成
        await bus.publish(EventEnvelope(
            type=AGENT_STEP_COMPLETED,
            session_id=child_sid,
            turn_id=record.active_turn_id,
            payload={"result": {"content": "done"}},
        ))
        payload = await asyncio.wait_for(waiter, timeout=5)
        assert payload["status"] == "completed"
        await coordinator.stop()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/test_agent_message_coordinator.py::TestAgentMessageCoordinator::test_heartbeat_resets_timeout -v`
Expected: FAIL — 当前 `_timeout_after` 是固定 sleep，0.3s 后会超时

- [ ] **Step 3: 实现心跳续期机制**

在 `agent_message_coordinator.py` 中：

**3a. 新增 import：**

```python
from sensenova_claw.kernel.events.types import (
    AGENT_MESSAGE_COMPLETED,
    AGENT_MESSAGE_FAILED,
    AGENT_MESSAGE_REQUESTED,
    AGENT_STEP_COMPLETED,
    ERROR_RAISED,
    LLM_CALL_COMPLETED,
    LLM_CALL_REQUESTED,
    SESSION_CREATED,
    TOOL_CALL_COMPLETED,
    TOOL_CALL_REQUESTED,
    USER_QUESTION_ASKED,
    USER_TURN_CANCEL_REQUESTED,
)
```

**3b. 新增类常量和字段（在 `__init__` 中）：**

```python
    HEARTBEAT_TYPES = {
        LLM_CALL_REQUESTED, LLM_CALL_COMPLETED,
        TOOL_CALL_REQUESTED, TOOL_CALL_COMPLETED,
        USER_QUESTION_ASKED,
    }

    def __init__(self, ...):
        # ... 现有字段 ...
        self._last_heartbeat: dict[str, float] = {}
```

**3c. 在 `_event_loop` 中新增心跳处理（独立 if 块，在 try 块末尾、现有 elif 链之后）：**

```python
    async def _event_loop(self) -> None:
        async for event in self._bus.subscribe():
            try:
                if event.type == AGENT_MESSAGE_REQUESTED:
                    await self._handle_message_requested(event)
                elif event.type == AGENT_STEP_COMPLETED:
                    await self._handle_child_completed(event)
                elif event.type == ERROR_RAISED:
                    await self._handle_child_failed(event)
                elif event.type == USER_TURN_CANCEL_REQUESTED:
                    await self._handle_cancel_requested(event)
                # 心跳续期（独立 if，不与上面 elif 冲突）
                if event.type in self.HEARTBEAT_TYPES:
                    record_id = self._child_session_index.get(event.session_id)
                    if record_id and record_id in self._last_heartbeat:
                        self._last_heartbeat[record_id] = time.time()
            except Exception:  # noqa: BLE001
                logger.exception("AgentMessageCoordinator 处理事件失败")
```

**3d. 在 `_handle_message_requested` 中，`record.status = "running"` 之后初始化心跳时间：**

```python
        record.status = "running"
        record.active_turn_id = turn_id
        await self._repo.update_message_record(record)
        self._last_heartbeat[record.id] = time.time()  # 新增
        self._ensure_timeout_watch(record)
```

**3e. 替换 `_timeout_after` 为 `_heartbeat_timeout_watch`：**

```python
    async def _timeout_after(self, record_id: str, timeout_seconds: float) -> None:
        """心跳无活动超时检查：循环检查 last_heartbeat，超过 timeout 才触发超时。"""
        interval = min(max(timeout_seconds / 3, 0.05), 30)
        try:
            while True:
                await asyncio.sleep(interval)
                record = await self._repo.get_message_record(record_id)
                if not record or record.status in self.FINAL_STATUSES:
                    return
                last_hb = self._last_heartbeat.get(record_id, 0)
                if time.time() - last_hb > timeout_seconds:
                    await self.cancel_message(
                        record_id=record_id,
                        reason=f"send_message 无活动超时（{timeout_seconds} 秒）",
                        status="timed_out",
                        propagate_to_child=True,
                        source_session_id=record.parent_session_id or None,
                    )
                    return
        except asyncio.CancelledError:
            raise
        finally:
            task = self._timeout_tasks.get(record_id)
            if task is asyncio.current_task():
                self._timeout_tasks.pop(record_id, None)
```

**3f. 在 `_cancel_record_tasks` 中清理心跳：**

```python
    def _cancel_record_tasks(self, record_id: str) -> None:
        self._cancel_timeout_task(record_id)
        self._cancel_retry_task(record_id)
        self._last_heartbeat.pop(record_id, None)  # 新增
```

**3g. 在 `_retry_after_backoff` 中，`record.status = "running"` 之后重置心跳并重启 watch：**

```python
            record.status = "running"
            record.active_turn_id = turn_id
            await self._repo.update_message_record(record)
            self._last_heartbeat[record.id] = time.time()  # 新增
            self._ensure_timeout_watch(record)  # 新增
```

- [ ] **Step 4: 运行心跳续期测试确认通过**

Run: `python3 -m pytest tests/unit/test_agent_message_coordinator.py::TestAgentMessageCoordinator::test_heartbeat_resets_timeout -v`
Expected: PASS

- [ ] **Step 5: 运行现有超时测试确认仍通过**

Run: `python3 -m pytest tests/unit/test_agent_message_coordinator.py::TestAgentMessageCoordinator::test_timeout_watch_marks_record_timed_out -v`
Expected: PASS（无心跳 = 无活动 = 仍然超时，行为不变）

- [ ] **Step 6: Commit**

```bash
git add sensenova_claw/kernel/runtime/agent_message_coordinator.py tests/unit/test_agent_message_coordinator.py
git commit -m "feat(coordinator): 实现心跳续期超时机制"
```

---

### Task 5: 补充心跳相关单元测试

**Files:**
- Modify: `tests/unit/test_agent_message_coordinator.py`

- [ ] **Step 1: 新增测试 — 无心跳超时**

```python
    async def test_no_heartbeat_triggers_timeout(self, test_repo):
        """子 Agent 无活动超过 timeout 应触发超时"""
        bus = PublicEventBus()
        runtime = _FakeAgentRuntime()
        coordinator = AgentMessageCoordinator(
            bus=bus, repo=test_repo, agent_runtime=runtime,
        )
        await coordinator.start()
        waiter = coordinator.register_sync_waiter("record_no_hb")

        await bus.publish(EventEnvelope(
            type=AGENT_MESSAGE_REQUESTED,
            session_id="parent",
            trace_id="record_no_hb",
            payload={
                "record_id": "record_no_hb",
                "target_id": "helper",
                "message": "无心跳任务",
                "mode": "sync",
                "depth": 1,
                "send_chain": ["default"],
                "parent_session_id": "parent",
                "timeout_seconds": 0.3,
                "max_retries": 0,
            },
        ))
        # 不发任何心跳，等待超时
        payload = await asyncio.wait_for(waiter, timeout=5)
        assert payload["status"] == "timed_out"

        record = await test_repo.get_message_record("record_no_hb")
        assert record is not None
        assert record.status == "timed_out"
        await coordinator.stop()
```

- [ ] **Step 2: 新增测试 — 清理验证**

```python
    async def test_heartbeat_cleanup_on_completion(self, test_repo):
        """任务完成后 _last_heartbeat 应被清理"""
        bus = PublicEventBus()
        runtime = _FakeAgentRuntime()
        coordinator = AgentMessageCoordinator(
            bus=bus, repo=test_repo, agent_runtime=runtime,
        )
        await coordinator.start()

        await bus.publish(EventEnvelope(
            type=AGENT_MESSAGE_REQUESTED,
            session_id="parent",
            trace_id="record_cleanup",
            payload={
                "record_id": "record_cleanup",
                "target_id": "helper",
                "message": "清理测试",
                "mode": "async",
                "depth": 1,
                "send_chain": ["default"],
                "parent_session_id": "parent",
                "timeout_seconds": 30,
                "max_retries": 0,
            },
        ))
        await asyncio.sleep(0.1)
        assert "record_cleanup" in coordinator._last_heartbeat

        record = await test_repo.get_message_record("record_cleanup")
        await bus.publish(EventEnvelope(
            type=AGENT_STEP_COMPLETED,
            session_id=record.child_session_id,
            turn_id=record.active_turn_id,
            payload={"result": {"content": "done"}},
        ))
        await asyncio.sleep(0.1)
        assert "record_cleanup" not in coordinator._last_heartbeat
        await coordinator.stop()
```

- [ ] **Step 3: 新增测试 — 并发隔离**

```python
    async def test_heartbeat_isolation_between_records(self, test_repo):
        """两个并行 delegation，一个有心跳一个没有，验证互不影响"""
        bus = PublicEventBus()
        runtime = _FakeAgentRuntime()
        coordinator = AgentMessageCoordinator(
            bus=bus, repo=test_repo, agent_runtime=runtime,
        )
        await coordinator.start()
        waiter_a = coordinator.register_sync_waiter("record_a")

        # 创建 record_a（短超时，无心跳 → 应超时）
        await bus.publish(EventEnvelope(
            type=AGENT_MESSAGE_REQUESTED,
            session_id="parent",
            trace_id="record_a",
            payload={
                "record_id": "record_a",
                "target_id": "helper",
                "message": "任务A",
                "mode": "sync",
                "depth": 1,
                "send_chain": ["default"],
                "parent_session_id": "parent",
                "timeout_seconds": 0.3,
                "max_retries": 0,
            },
        ))
        await asyncio.sleep(0.05)

        # 创建 record_b（长超时，有心跳 → 不应超时）
        await bus.publish(EventEnvelope(
            type=AGENT_MESSAGE_REQUESTED,
            session_id="parent2",
            trace_id="record_b",
            payload={
                "record_id": "record_b",
                "target_id": "helper",
                "message": "任务B",
                "mode": "async",
                "depth": 1,
                "send_chain": ["default"],
                "parent_session_id": "parent2",
                "timeout_seconds": 0.3,
                "max_retries": 0,
            },
        ))
        await asyncio.sleep(0.05)

        record_b = await test_repo.get_message_record("record_b")
        child_b = record_b.child_session_id

        # 只给 record_b 发心跳
        for _ in range(3):
            await asyncio.sleep(0.15)
            await bus.publish(EventEnvelope(
                type=TOOL_CALL_COMPLETED,
                session_id=child_b,
                payload={},
            ))

        # record_a 应已超时
        payload_a = await asyncio.wait_for(waiter_a, timeout=5)
        assert payload_a["status"] == "timed_out"

        # record_b 应仍在运行
        record_b = await test_repo.get_message_record("record_b")
        assert record_b.status == "running"
        await coordinator.stop()
```

- [ ] **Step 4: 新增测试 — 无关 session 事件不影响计时器**

```python
    async def test_unrelated_session_heartbeat_ignored(self, test_repo):
        """非子 session 的心跳事件不应影响任何 record 的计时器"""
        bus = PublicEventBus()
        runtime = _FakeAgentRuntime()
        coordinator = AgentMessageCoordinator(
            bus=bus, repo=test_repo, agent_runtime=runtime,
        )
        await coordinator.start()
        waiter = coordinator.register_sync_waiter("record_unrelated")

        await bus.publish(EventEnvelope(
            type=AGENT_MESSAGE_REQUESTED,
            session_id="parent",
            trace_id="record_unrelated",
            payload={
                "record_id": "record_unrelated",
                "target_id": "helper",
                "message": "无关测试",
                "mode": "sync",
                "depth": 1,
                "send_chain": ["default"],
                "parent_session_id": "parent",
                "timeout_seconds": 0.3,
                "max_retries": 0,
            },
        ))
        await asyncio.sleep(0.05)

        # 发送来自无关 session 的心跳
        for _ in range(3):
            await asyncio.sleep(0.15)
            await bus.publish(EventEnvelope(
                type=LLM_CALL_REQUESTED,
                session_id="totally_unrelated_session",
                payload={},
            ))

        # 应仍然超时（无关心跳不续期）
        payload = await asyncio.wait_for(waiter, timeout=5)
        assert payload["status"] == "timed_out"
        await coordinator.stop()
```

- [ ] **Step 5: 运行所有新增测试**

Run: `python3 -m pytest tests/unit/test_agent_message_coordinator.py -v`
Expected: 全部通过（包括原有 4 个 + 新增 5 个）

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_agent_message_coordinator.py
git commit -m "test(coordinator): 补充心跳续期相关单元测试"
```

---

### Task 6: 全量回归测试

- [ ] **Step 1: 运行全部单元测试**

Run: `python3 -m pytest tests/unit/ -q --timeout=30`
Expected: 全部通过

- [ ] **Step 2: 运行集成测试（如果可用）**

Run: `python3 -m pytest tests/integration/ -q --timeout=60`
Expected: 全部通过

- [ ] **Step 3: Commit（如有修复）**

如果回归测试发现问题，修复后提交。
