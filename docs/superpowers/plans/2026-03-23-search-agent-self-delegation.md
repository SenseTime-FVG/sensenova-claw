# Search Agent 自我委派并行搜索 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 search-agent 能够自主拆分复杂搜索任务为多个子任务，通过 `send_message` 向自己的新 session 并行委派执行，最后汇总结果。

**Architecture:** 修改 `get_sendable` 允许自身出现在可发送列表中，放宽 `send_message` 循环检测允许自我委派，调整 search-agent 的 `max_send_depth` 和 system prompt 引导自主拆分。

**Tech Stack:** Python 3.12, asyncio, pytest

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `agentos/capabilities/agents/registry.py:60-63` | `get_sendable` 不再排除自身 |
| Modify | `agentos/capabilities/tools/send_message_tool.py:229` | 循环检测允许自我委派 |
| Modify | `.agentos/agents/search-agent/config.yml:30` | `max_send_depth: 1` → `2` |
| Modify | `.agentos/agents/search-agent/SYSTEM_PROMPT.md` | 追加任务拆分与并行执行指引 |
| Modify | `tests/unit/test_agent_registry.py` | 新增 `get_sendable` 包含自身的测试 |
| Modify | `tests/integration/test_send_message_tool.py` | 新增自我委派和循环检测测试 |

---

### Task 0: 修复集成测试文件语法错误

**Files:**
- Modify: `tests/integration/test_send_message_tool.py:36`

- [ ] **Step 1: 修复语法错误**

在 `tests/integration/test_send_message_tool.py` 第 36 行，将：

```python
    registry = AgentRegistry() / "agents")
```

改为：

```python
    registry = AgentRegistry(agentos_home=tmp_path / "agents")
```

- [ ] **Step 2: 运行现有集成测试确认可导入**

Run: `python3 -m pytest tests/integration/test_send_message_tool.py --collect-only`
Expected: 成功收集测试用例，无 SyntaxError

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_send_message_tool.py
git commit -m "fix: syntax error in send_message integration test"
```

---

### Task 1: get_sendable 允许自身 — 测试

**Files:**
- Modify: `tests/unit/test_agent_registry.py`

- [ ] **Step 1: 写失败测试 — get_sendable 空白名单时包含自身**

在 `tests/unit/test_agent_registry.py` 末尾追加：

```python
def test_get_sendable_includes_self_when_empty_whitelist(self):
    """空 can_send_message_to 时，get_sendable 应包含自身（支持自我委派）"""
    r = AgentRegistry()
    r.register(AgentConfig.create(id="search", name="Search", can_send_message_to=[]))
    r.register(AgentConfig.create(id="helper", name="Helper"))
    sendable_ids = [a.id for a in r.get_sendable("search")]
    assert "search" in sendable_ids
    assert "helper" in sendable_ids
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/test_agent_registry.py::TestAgentRegistry::test_get_sendable_includes_self_when_empty_whitelist -v`
Expected: FAIL — `"search" not in sendable_ids`（当前 `get_sendable` 排除自身）

- [ ] **Step 3: 写失败测试 — 显式白名单不受影响**

在 `tests/unit/test_agent_registry.py` 末尾追加：

```python
def test_get_sendable_explicit_whitelist_unchanged(self):
    """显式 can_send_message_to 列表行为不变"""
    r = AgentRegistry()
    r.register(AgentConfig.create(id="main", name="M", can_send_message_to=["a"]))
    r.register(AgentConfig.create(id="a", name="A"))
    r.register(AgentConfig.create(id="b", name="B"))
    sendable_ids = [a.id for a in r.get_sendable("main")]
    assert sendable_ids == ["a"]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/test_agent_registry.py::TestAgentRegistry::test_get_sendable_explicit_whitelist_unchanged -v`
Expected: PASS（显式白名单逻辑未改动）

- [ ] **Step 5: Commit 测试**

```bash
git add tests/unit/test_agent_registry.py
git commit -m "test: add get_sendable self-inclusion tests"
```

---

### Task 2: get_sendable 允许自身 — 实现

**Files:**
- Modify: `agentos/capabilities/agents/registry.py:60-63`

- [ ] **Step 1: 修改 get_sendable**

在 `agentos/capabilities/agents/registry.py` 第 60-63 行，将：

```python
if not source.can_send_message_to:
    # 空列表 = 可以向所有其他已启用 Agent 发送消息
    return [a for a in self._agents.values()
            if a.id != from_agent_id and a.enabled]
```

改为：

```python
if not source.can_send_message_to:
    # 空列表 = 可以向所有已启用 Agent 发送消息（含自身，支持自我委派）
    return [a for a in self._agents.values() if a.enabled]
```

- [ ] **Step 2: 运行全部 registry 测试**

Run: `python3 -m pytest tests/unit/test_agent_registry.py -v`
Expected: ALL PASS

注意：`test_get_delegatable_all` 原来断言 `any(a.id == "h" ...)` 不检查自身，改动后仍然通过。

- [ ] **Step 3: Commit**

```bash
git add agentos/capabilities/agents/registry.py
git commit -m "feat: allow self in get_sendable for self-delegation"
```

---

### Task 3: 循环检测放宽 — 测试

**Files:**
- Modify: `tests/integration/test_send_message_tool.py`

- [ ] **Step 1: 写失败测试 — 自我委派应通过**

在 `tests/integration/test_send_message_tool.py` 的 `TestSendMessageTool` 类末尾追加：

```python
async def test_self_delegation_allowed(self, test_repo, tmp_path):
    """agent 向自己发送消息（自我委派）应被允许"""
    bus, bus_router, registry, runtime, coordinator = await _build_runtime(test_repo, tmp_path)
    registry.register(AgentConfig.create(id="searcher", name="Searcher", max_send_depth=2))
    await test_repo.create_session(
        "parent",
        meta={"agent_id": "searcher", "send_depth": 0, "send_chain": ["searcher"]},
    )

    seen_child = asyncio.Event()

    async def fake_child():
        async for event in bus.subscribe():
            if event.type == USER_INPUT and event.session_id.startswith("agent2agent_"):
                seen_child.set()
                await bus.publish(
                    EventEnvelope(
                        type=AGENT_STEP_COMPLETED,
                        session_id=event.session_id,
                        source="test",
                        payload={"result": {"content": "self-delegated result"}},
                    )
                )
                return

    fake_task = asyncio.create_task(fake_child())
    await asyncio.sleep(0)

    tool = SendMessageTool(
        agent_registry=registry,
        bus=bus,
        repo=test_repo,
        coordinator=coordinator,
        timeout=5,
    )
    result = await tool.execute(
        target_agent="searcher",
        message="子任务",
        _session_id="parent",
        _turn_id="turn_1",
        _tool_call_id="tc_1",
    )

    assert "self-delegated result" in result
    assert seen_child.is_set()

    fake_task.cancel()
    await coordinator.stop()
    await runtime.stop()
    await bus_router.stop()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/integration/test_send_message_tool.py::TestSendMessageTool::test_self_delegation_allowed -v`
Expected: FAIL — `"循环链路"` in result（当前循环检测拦截自我委派）

- [ ] **Step 3: 写测试 — 真正循环仍被拦截**

在 `TestSendMessageTool` 类末尾追加：

```python
async def test_real_cycle_still_blocked(self, test_repo, tmp_path):
    """真正的循环（A→B→A）仍应被拦截"""
    bus, bus_router, registry, runtime, coordinator = await _build_runtime(test_repo, tmp_path)
    registry.register(AgentConfig.create(id="agent_a", name="A", max_send_depth=3))
    registry.register(AgentConfig.create(id="agent_b", name="B", max_send_depth=3))
    # 模拟 agent_b 的 session，send_chain 中包含 agent_a（A→B 链路）
    await test_repo.create_session(
        "b_session",
        meta={"agent_id": "agent_b", "send_depth": 1, "send_chain": ["agent_a", "agent_b"]},
    )

    tool = SendMessageTool(
        agent_registry=registry,
        bus=bus,
        repo=test_repo,
        coordinator=coordinator,
        timeout=5,
    )
    # agent_b 尝试向 agent_a 发消息 → 应被拦截
    result = await tool.execute(
        target_agent="agent_a",
        message="回环",
        _session_id="b_session",
        _turn_id="turn_b",
        _tool_call_id="tc_b",
    )

    assert "循环链路" in result

    await coordinator.stop()
    await runtime.stop()
    await bus_router.stop()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/integration/test_send_message_tool.py::TestSendMessageTool::test_real_cycle_still_blocked -v`
Expected: PASS（当前循环检测已拦截 A→B→A）

- [ ] **Step 5: 写测试 — 并行自我委派**

在 `TestSendMessageTool` 类末尾追加：

```python
async def test_parallel_self_delegation(self, test_repo, tmp_path):
    """多目标并行自我委派应全部成功"""
    bus, bus_router, registry, runtime, coordinator = await _build_runtime(test_repo, tmp_path)
    registry.register(AgentConfig.create(id="searcher", name="Searcher", max_send_depth=2))
    await test_repo.create_session(
        "parent",
        meta={"agent_id": "searcher", "send_depth": 0, "send_chain": ["searcher"]},
    )

    child_count = 0

    async def fake_children():
        nonlocal child_count
        async for event in bus.subscribe():
            if event.type == USER_INPUT and event.session_id.startswith("agent2agent_"):
                child_count += 1
                await bus.publish(
                    EventEnvelope(
                        type=AGENT_STEP_COMPLETED,
                        session_id=event.session_id,
                        source="test",
                        payload={"result": {"content": f"result-{child_count}"}},
                    )
                )
                if child_count >= 3:
                    return

    fake_task = asyncio.create_task(fake_children())
    await asyncio.sleep(0)

    tool = SendMessageTool(
        agent_registry=registry,
        bus=bus,
        repo=test_repo,
        coordinator=coordinator,
        timeout=5,
    )
    result = await tool.execute(
        targets=[
            {"target_agent": "searcher", "message": "[子任务模式] 任务1"},
            {"target_agent": "searcher", "message": "[子任务模式] 任务2"},
            {"target_agent": "searcher", "message": "[子任务模式] 任务3"},
        ],
        mode="sync",
        timeout_seconds=5,
        _session_id="parent",
        _turn_id="turn_1",
        _tool_call_id="tc_1",
    )

    assert isinstance(result, list)
    assert len(result) == 3
    assert all(r["status"] == "completed" for r in result)

    fake_task.cancel()
    await coordinator.stop()
    await runtime.stop()
    await bus_router.stop()
```

- [ ] **Step 6: Commit 测试**

```bash
git add tests/integration/test_send_message_tool.py
git commit -m "test: add self-delegation and cycle detection tests"
```

---

### Task 4: 循环检测放宽 — 实现

**Files:**
- Modify: `agentos/capabilities/tools/send_message_tool.py:229-231`

- [ ] **Step 1: 修改循环检测条件**

在 `agentos/capabilities/tools/send_message_tool.py` 第 229-231 行，将：

```python
            if target_id in current_send_chain:
                chain_str = " -> ".join(current_send_chain + [target_id])
                return f"发送失败：检测到循环链路 {chain_str}。"
```

改为：

```python
            # 允许自我委派（同一 agent 的新 session），拦截真正的循环（A→B→A）
            if target_id in current_send_chain and target_id != current_agent_id:
                chain_str = " -> ".join(current_send_chain + [target_id])
                return f"发送失败：检测到循环链路 {chain_str}。"
```

- [ ] **Step 2: 运行全部 send_message 测试**

Run: `python3 -m pytest tests/integration/test_send_message_tool.py -v`
Expected: ALL PASS（包括 Task 3 新增的 3 个测试）

- [ ] **Step 3: 运行全部单元测试确认无回归**

Run: `python3 -m pytest tests/unit/ -q`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add agentos/capabilities/tools/send_message_tool.py
git commit -m "feat: allow self-delegation in cycle detection"
```

---

### Task 5: search-agent 配置调整

**Files:**
- Modify: `.agentos/agents/search-agent/config.yml`

- [ ] **Step 1: 修改 max_send_depth**

在 `.agentos/agents/search-agent/config.yml` 中，将：

```yaml
max_send_depth: 1
```

改为：

```yaml
max_send_depth: 2
```

- [ ] **Step 2: Commit**

```bash
git add .agentos/agents/search-agent/config.yml
git commit -m "config: increase search-agent max_send_depth to 2"
```

---

### Task 6: search-agent System Prompt 增强

**Files:**
- Modify: `.agentos/agents/search-agent/SYSTEM_PROMPT.md`

- [ ] **Step 1: 追加任务拆分指引**

在 `.agentos/agents/search-agent/SYSTEM_PROMPT.md` 末尾追加：

```markdown

## 任务拆分与并行执行

当你收到的任务带有 [子任务模式] 标记时，直接执行任务，不要再拆分。不要使用 ask_user 确认，直接执行搜索和分析。

当任务没有标记且满足以下条件时，你可以拆分为多个子任务并行执行：
- 任务包含多个独立的调研方向
- 各方向之间没有依赖关系
- 并行执行能显著提升效率

拆分方法：使用 send_message 的多目标模式向自己发送子任务：

\`\`\`json
{
  "targets": [
    {"target_agent": "search-agent", "message": "[子任务模式] 子任务描述1..."},
    {"target_agent": "search-agent", "message": "[子任务模式] 子任务描述2..."}
  ],
  "mode": "sync",
  "timeout_seconds": 600
}
\`\`\`

注意事项：
- 每个子任务的 message 必须以 [子任务模式] 开头
- 每个子任务应包含明确的调研范围和预期输出格式
- 子任务数量建议控制在 2-5 个，避免过度拆分
- 根据任务复杂度设置合理的 timeout_seconds（默认 600 秒）

所有子任务完成后，你需要：
- 整合各子任务的结果
- 去重和交叉验证
- 输出一份完整的汇总报告
```

- [ ] **Step 2: Commit**

```bash
git add .agentos/agents/search-agent/SYSTEM_PROMPT.md
git commit -m "config: add self-delegation parallel search guidance to search-agent prompt"
```

---

### Task 7: 最终验证

- [ ] **Step 1: 运行全部测试**

Run: `python3 -m pytest tests/unit/ tests/integration/ -q`
Expected: ALL PASS，无回归

- [ ] **Step 2: 检查改动文件清单**

Run: `git diff --stat HEAD~7`
Expected: 只有以下 6 个文件被修改：
- `agentos/capabilities/agents/registry.py`
- `agentos/capabilities/tools/send_message_tool.py`
- `.agentos/agents/search-agent/config.yml`
- `.agentos/agents/search-agent/SYSTEM_PROMPT.md`
- `tests/unit/test_agent_registry.py`
- `tests/integration/test_send_message_tool.py`

**注意：** 端到端集成测试（search-agent 收到复杂任务 → LLM 自主拆分 → 并行子 session → 汇总）需要真实 LLM API key，不在本计划范围内。可在手动测试或 e2e 测试中验证。
