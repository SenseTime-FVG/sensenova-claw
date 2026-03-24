# send_message 心跳续期超时机制设计

## 问题

当前 `send_message` 工具在 sync 模式下使用固定总超时（默认 300s）。子 Agent 执行长任务时，即使任务正常推进，超时到了调用方就会收到错误，子 Agent 的结果丢失。不同任务耗时差异大，固定超时无法覆盖所有场景。

## 方案

将 `timeout_seconds` 的语义从"总耗时上限"改为"无活动超时"。子 Agent 执行过程中，EventBus 上已有的事件作为心跳信号，coordinator 收到心跳后重置超时计时器。只有子 Agent 真正无活动（卡死）时才触发超时。

不需要 `max_timeout` 绝对上限，因为子 Agent 已有以下保护机制：
- 最大工具调用轮次限制（防无效循环）
- 单次工具执行超时（防工具卡死）
- LLM 调用超时（防 API 卡死）

## 心跳事件源

监听子 Agent session 的以下四个事件作为心跳信号：

- `llm.call_requested` — LLM 调用开始
- `llm.call_completed` — LLM 调用完成
- `tool.call_requested` — 工具调用开始
- `tool.call_completed` — 工具调用完成

选择理由：覆盖每个关键步骤的开始和结束。比如一个工具执行了 4 分钟，`tool.call_requested` 在开始时就重置了计时器，不会因为工具执行慢而误判超时。

不监听 `agent.step_completed`，因为它是一轮结束的标志，到那时任务可能已经完成，没有续期意义。

## 实现变更

### AgentMessageCoordinator

1. 新增内存字段 `_last_heartbeat: dict[str, float]`，key 为 record_id
2. 新增 `_child_session_index` 到 record_id 的反查（如果尚未存在）
3. 启动 timeout watch 时，注册 EventBus 订阅监听子 session 的四个心跳事件
4. timeout watch task 改为循环检查模式

#### 心跳监听

```python
def _on_child_heartbeat(self, event: EventEnvelope):
    """收到子 session 的心跳事件，重置超时计时器"""
    record_id = self._child_session_index.get(event.session_id)
    if record_id and record_id in self._last_heartbeat:
        self._last_heartbeat[record_id] = time.time()
```

#### 超时检查（替换原有 `_ensure_timeout_watch`）

```python
async def _heartbeat_timeout_watch(self, record_id: str, timeout: float):
    """循环检查无活动时间，超过 timeout 才触发超时"""
    interval = max(timeout / 3, 10)
    while True:
        await asyncio.sleep(interval)
        record = self._records.get(record_id)
        if not record or record.status not in ("running", "retrying"):
            return
        elapsed = time.time() - self._last_heartbeat[record_id]
        if elapsed > timeout:
            await self.cancel_message(
                record_id, status="timed_out", propagate_to_child=True
            )
            return
```

#### 生命周期管理

- 创建 record 时：`_last_heartbeat[record_id] = time.time()`，注册心跳订阅
- 任务完成/取消时：删除 `_last_heartbeat[record_id]`，取消心跳订阅，取消 watch task
- retry 时：重置 `_last_heartbeat[record_id] = time.time()`

### 配置

无新增配置项。`delegation.default_timeout`（默认 300s）语义从"总耗时上限"变为"无活动超时"。`send_message` 工具的 `timeout_seconds` 参数含义同步变化。

### send_message_tool

无代码改动。`timeout_seconds` 参数保留，语义自然跟随 coordinator 变化。

## 边界情况

1. **心跳订阅失败**：降级为当前行为（固定总超时）
2. **首次 LLM 调用慢**：`last_heartbeat_time` 初始值为 record 创建时间，首次调用受 `timeout_seconds` 保护；LLM 调用自身超时会先兜住
3. **并发多个 delegation**：每个 record 独立维护 `last_heartbeat_time`，互不影响
4. **retry 场景**：重试时重置 `last_heartbeat_time`，重新开始心跳监听

## 测试

### 单元测试（test_agent_message_coordinator.py）

1. **心跳续期**：子 Agent 在 timeout 内发心跳，验证计时器重置、不超时
2. **无心跳超时**：子 Agent 无活动超过 timeout，验证触发超时取消
3. **清理**：任务完成后，验证心跳订阅和 watch task 被正确清理

### 集成测试（test_send_message_tool.py）

1. 修改现有超时测试用例，适配心跳语义
2. 新增：子 Agent 执行多步长任务（每步有事件），总耗时超过 timeout_seconds 但不超时

## 改动范围

- `agent_message_coordinator.py`：改 timeout watch 逻辑 + 加心跳订阅（约 40-50 行）
- `test_agent_message_coordinator.py`：新增 3 个测试用例
- `test_send_message_tool.py`：修改 1 个、新增 1 个测试用例
- 配置/工具参数：无变更
