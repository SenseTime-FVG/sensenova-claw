# send_message 心跳续期超时机制设计

## 问题

当前 `send_message` 工具在 sync 模式下使用固定总超时（默认 300s）。子 Agent 执行长任务时，即使任务正常推进，超时到了调用方就会收到错误，子 Agent 的结果丢失。不同任务耗时差异大，固定超时无法覆盖所有场景。

## 方案

将 `timeout_seconds` 的语义从"总耗时上限"改为"无活动超时"。子 Agent 执行过程中，EventBus 上已有的事件作为心跳信号，coordinator 收到心跳后重置超时计时器。只有子 Agent 真正无活动（卡死）时才触发超时。

不需要 `max_timeout` 绝对上限，因为子 Agent 有以下保护机制：
- 最大工具调用轮次限制（防无效循环）— 需扩展到 delegation session，见下文
- 单次工具执行超时（防工具卡死）
- LLM 调用超时（防 API 卡死）

### 前置修复：delegation session 轮次限制

当前 `agent_worker.py` 中 `max_tool_calls` / `max_llm_calls` 检查仅在 `_is_proactive_session()` 为 true 时生效（通过 `session_meta` 中的 `proactive_job_id` 判断）。delegation session 没有此标记，因此没有轮次限制保护。

修复方案：将轮次限制检查从"仅 proactive session"扩展为"proactive session 或 delegation session"。

1. `agent_worker.py` 中新增 `_is_autonomous_session()` 方法，当 `session_meta` 包含 `proactive_job_id` 或 `message_trace_id`（delegation 标记）时返回 true
2. 将 `_is_proactive_session()` 的调用点替换为 `_is_autonomous_session()`
3. delegation session 的 `max_tool_calls` / `max_llm_calls` 从 delegation 配置中读取，coordinator 在 `spawn_agent_session` 时通过 `meta` 传入

配置新增：
```python
"delegation": {
    "max_depth": 3,
    "default_timeout": 300,
    "max_tool_calls": 30,       # delegation session 工具调用上限
    "max_llm_calls": 15,        # delegation session LLM 调用上限
    "retry": { ... },
    "enabled": True,
}
```

## 心跳事件源

监听子 Agent session 的以下事件作为心跳信号：

- `llm.call_requested` — LLM 调用开始
- `llm.call_completed` — LLM 调用完成
- `tool.call_requested` — 工具调用开始
- `tool.call_completed` — 工具调用完成
- `user.question_asked` — 子 Agent 调用 ask_user 等待用户输入

选择理由：覆盖每个关键步骤的开始和结束。比如一个工具执行了 4 分钟，`tool.call_requested` 在开始时就重置了计时器，不会因为工具执行慢而误判超时。`user.question_asked` 防止子 Agent 等待用户输入时被误判超时。

不监听 `agent.step_completed`，因为它是一轮结束的标志，到那时任务可能已经完成，没有续期意义。

## 实现变更

### AgentMessageCoordinator

1. 新增内存字段 `_last_heartbeat: dict[str, float]`，key 为 record_id
2. 在现有 `_event_loop` 中增加心跳事件处理分支（复用已有的 EventBus 订阅，不新建订阅）
3. timeout watch task 改为循环检查模式

#### 心跳处理（在现有 `_event_loop` 中新增分支）

```python
HEARTBEAT_TYPES = {
    "llm.call_requested", "llm.call_completed",
    "tool.call_requested", "tool.call_completed",
    "user.question_asked",
}

# 在 _event_loop 的事件分发中新增：
if event.type in HEARTBEAT_TYPES:
    record_id = self._child_session_index.get(event.session_id)
    if record_id and record_id in self._last_heartbeat:
        self._last_heartbeat[record_id] = time.time()
```

#### 超时检查（替换原有 `_timeout_after`）

```python
async def _heartbeat_timeout_watch(self, record_id: str, timeout: float):
    """循环检查无活动时间，超过 timeout 才触发超时"""
    interval = min(max(timeout / 3, 1), 30)
    while True:
        await asyncio.sleep(interval)
        record = await self._repo.get_message_record(record_id)
        if not record or record.status not in ("running", "retrying"):
            return
        elapsed = time.time() - self._last_heartbeat.get(record_id, 0)
        if elapsed > timeout:
            await self.cancel_message(
                record_id,
                reason=f"无活动超时 ({timeout}s)",
                status="timed_out",
                propagate_to_child=True,
            )
            return
```

#### 生命周期管理

- 创建 record 时：`_last_heartbeat[record_id] = time.time()`
- 任务完成/取消时：删除 `_last_heartbeat[record_id]`，取消 watch task
- retry 时：重置 `_last_heartbeat[record_id] = time.time()`，重启 watch task

### 配置

无新增配置项。`delegation.default_timeout`（默认 300s）语义从"总耗时上限"变为"无活动超时"。`send_message` 工具的 `timeout_seconds` 参数含义同步变化。

### send_message_tool

无代码改动。`timeout_seconds` 参数保留，语义自然跟随 coordinator 变化。

## 边界情况

1. **首次 LLM 调用慢**：`last_heartbeat_time` 初始值为 record 创建时间，首次调用受 `timeout_seconds` 保护；LLM 调用自身超时会先兜住
2. **并发多个 delegation**：每个 record 独立维护 `last_heartbeat_time`，互不影响；心跳事件通过 `_child_session_index` 精确匹配到对应 record
3. **retry 场景**：重试时重置 `last_heartbeat_time`，重启 watch task
4. **ask_user 等待**：`user.question_asked` 事件作为心跳，防止等待用户输入时误判超时
5. **无关 session 的事件**：通过 `_child_session_index` 过滤，不会影响其他 record 的计时器

## 测试

### 单元测试（test_agent_message_coordinator.py）

1. **心跳续期**：子 Agent 在 timeout 内发心跳，验证计时器重置、不超时
2. **无心跳超时**：子 Agent 无活动超过 timeout，验证触发超时取消
3. **清理**：任务完成后，验证 `_last_heartbeat` 和 watch task 被正确清理
4. **并发隔离**：两个并行 delegation，一个有心跳一个没有，验证互不影响
5. **无关 session 事件**：非子 session 的心跳事件不影响计时器

### 集成测试（test_send_message_tool.py）

1. 修改现有超时测试用例，适配心跳语义
2. 新增：子 Agent 执行多步长任务（每步有事件），总耗时超过 timeout_seconds 但不超时

### agent_worker 轮次限制测试

1. delegation session 触发 `max_tool_calls` 限制，验证强制完成
2. delegation session 触发 `max_llm_calls` 限制，验证强制完成

## 改动范围

- `agent_worker.py`：新增 `_is_autonomous_session()` 方法，替换轮次限制检查条件（约 10 行）
- `agent_message_coordinator.py`：改 timeout watch 逻辑 + 在 `_event_loop` 中加心跳处理 + spawn 时传入轮次限制 meta（约 40-50 行）
- `config.py`：delegation 配置新增 `max_tool_calls`、`max_llm_calls` 默认值（2 行）
- `test_agent_message_coordinator.py`：新增 5 个测试用例
- `test_send_message_tool.py`：修改 1 个、新增 1 个测试用例
- `test_agent_worker.py`（如存在）：新增 2 个 delegation 轮次限制测试
