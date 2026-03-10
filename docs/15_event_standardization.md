# 事件系统标准化 PRD

## 背景

当前事件系统存在两个主要问题：

1. **事件对称性不足**：LLM 事件已具备 `requested → started → result → completed` 四阶段生命周期，但 Tool 事件缺少 `tool.call_result` 阶段，将结果数据直接放在 `tool.call_completed` 中，导致"结果内容"与"流程结束信号"耦合。
2. **事件命名不准确**：`ui.user_input` 等以 `ui.` 为前缀的事件名暗示来源为前端 UI，但实际用户输入也可能来自 CLI、TUI 或脚本调用，命名与语义不匹配。

## 目标

- 统一 LLM 和 Tool 的事件生命周期为对称的四阶段模式
- 将 `ui.*` 事件重命名为 `user.*`，准确反映事件语义

## 与双总线架构的关系

本 PRD 与 [14_dual_bus_architecture.md](./14_dual_bus_architecture.md) 协同设计。在双总线架构下：

- 事件的**生命周期和命名规范**由本 PRD 定义
- 事件的**流转路径**（PublicEventBus → BusRouter → PrivateEventBus → 回流）由双总线 PRD 定义
- 事件处理逻辑在 **SessionWorker** 中执行（订阅 PrivateEventBus），而非 Runtime 直接订阅 PublicEventBus

---

## 一、事件生命周期标准化

### 1.1 标准事件生命周期

**执行层**的异步任务（LLM 调用、Tool 执行）统一遵循四阶段生命周期：

```
requested → started → result → completed
```

- **requested**：请求发起，携带调用参数
- **started**：执行开始，表示任务已被接收
- **result**：执行结果，携带实际返回内容
- **completed**：流程结束，携带摘要（名称、成功/失败），不携带结果内容

**编排层**（Agent 事件）不适用此模式。Agent 作为流程编排器，其 `step_started` / `step_completed` 是控制信号而非执行结果，不需要 `result` 阶段。Agent 的"结果"就是最终 `step_completed` 中的 `final_response`。

### 1.2 当前 LLM 事件（已符合规范）

```python
LLM_CALL_REQUESTED = "llm.call_requested"    # 请求调用 LLM
LLM_CALL_STARTED = "llm.call_started"        # LLM 开始处理
LLM_CALL_RESULT = "llm.call_result"          # LLM 返回结果（携带 response）
LLM_CALL_COMPLETED = "llm.call_completed"    # LLM 调用流程结束（不携带内容）
```

### 1.3 改造后的 Tool 事件

```python
# 改造前
TOOL_CALL_REQUESTED = "tool.call_requested"
TOOL_CALL_STARTED = "tool.call_started"
TOOL_EXECUTION_START = "tool.execution_start"   # 待移除：与 started 语义重复
TOOL_EXECUTION_END = "tool.execution_end"       # 待移除：与 completed 语义重复
TOOL_CALL_COMPLETED = "tool.call_completed"     # 当前同时携带结果和终止信号

# 改造后
TOOL_CALL_REQUESTED = "tool.call_requested"     # 请求执行工具
TOOL_CALL_STARTED = "tool.call_started"         # 工具开始执行
TOOL_CALL_RESULT = "tool.call_result"           # 【新增】工具返回结果
TOOL_CALL_COMPLETED = "tool.call_completed"     # 工具执行流程结束
```

### 1.4 Tool 事件 Payload 变更

#### tool.call_result（新增）

承载执行结果的完整数据：

```python
{
    "tool_call_id": str,
    "tool_name": str,
    "result": Any,          # 工具执行结果
    "success": bool,        # 是否成功
    "error": str            # 错误信息（失败时）
}
```

#### tool.call_completed（变更）

仅作为终止信号，但保留摘要信息供监控/日志使用：

```python
# 改造后（终止信号 + 摘要）
{
    "tool_call_id": str,
    "tool_name": str,       # 保留：监控和日志需要，无需关联 result 事件
    "success": bool         # 保留：便于统计成功/失败率，无需关联 result 事件
}
```

> **设计决策**：`completed` 保留 `tool_name` 和 `success` 摘要字段。
> 只订阅 `completed` 的监控系统也能从单个事件中判断"哪个工具"和"是否成功"，
> 不必关联 `result` 事件。移除的只是体积大的 `result` 内容。

### 1.5 移除冗余事件

`tool.execution_start` 和 `tool.execution_end` 与 `tool.call_started` / `tool.call_completed` 语义重复，合并移除：

```python
# 移除以下常量
TOOL_EXECUTION_START = "tool.execution_start"   # → 合并到 tool.call_started
TOOL_EXECUTION_END = "tool.execution_end"       # → 合并到 tool.call_completed
```

### 1.6 涉及模块改动

在双总线架构下，事件处理逻辑位于 SessionWorker（订阅 PrivateEventBus），而非 Runtime 直接订阅 PublicEventBus：

```python
class ToolSessionWorker:
    """每会话一个，订阅 PrivateEventBus"""

    async def _handle_tool_requested(self, event: EventEnvelope) -> None:
        # 1. 发布 tool.call_started 到 PrivateEventBus
        await self.bus.publish(EventEnvelope(type=TOOL_CALL_STARTED, ...))
        # 2. 通过 Runtime 的共享 ToolRegistry 查找并执行工具
        tool = self.rt.registry.get(tool_name)
        result = await tool.execute(**arguments)
        # 3. 发布 tool.call_result 到 PrivateEventBus（携带执行结果）
        await self.bus.publish(EventEnvelope(type=TOOL_CALL_RESULT,
            payload={"tool_call_id": ..., "tool_name": ..., "result": result, "success": True}
        ))
        # 4. 发布 tool.call_completed 到 PrivateEventBus（摘要：tool_name + success）
        await self.bus.publish(EventEnvelope(type=TOOL_CALL_COMPLETED,
            payload={"tool_call_id": ..., "tool_name": ..., "success": True}
        ))


class AgentSessionWorker:
    """每会话一个，订阅 PrivateEventBus"""

    async def _loop(self) -> None:
        async for event in self.bus.subscribe():
            # 无需过滤 session_id —— PrivateEventBus 保证物理隔离
            if event.type == USER_INPUT:
                await self._handle_user_input(event)
            elif event.type == LLM_CALL_RESULT:
                await self._handle_llm_result(event)
            elif event.type == LLM_CALL_COMPLETED:
                await self._handle_llm_completed(event)
            elif event.type == TOOL_CALL_RESULT:        # 监听 result 事件获取工具结果
                await self._handle_tool_result(event)
            # tool.call_completed 不再处理业务逻辑
            # （回流到 PublicEventBus 后供事件持久化和监控消费）
```

---

## 二、事件命名规范化（ui → user）

### 2.1 重命名映射

```python
# 改造前                              # 改造后
UI_USER_INPUT = "ui.user_input"      → USER_INPUT = "user.input"
UI_TURN_CANCEL_REQUESTED             → USER_TURN_CANCEL_REQUESTED = "user.turn_cancel_requested"
```

### 2.2 理由

| 来源 | 旧前缀 `ui.*` | 新前缀 `user.*` |
|------|-------------|---------------|
| Web 前端 | 匹配 | 匹配 |
| CLI 客户端 | 不匹配 | 匹配 |
| TUI 客户端 | 不匹配 | 匹配 |
| 脚本/API 调用 | 不匹配 | 匹配 |

### 2.3 涉及模块改动

```python
# backend/app/events/types.py
USER_INPUT = "user.input"
USER_TURN_CANCEL_REQUESTED = "user.turn_cancel_requested"

# 需要同步更新的模块：
# - AgentRuntime._bootstrap_loop()（监听 user.input 触发 Worker 创建）
# - AgentSessionWorker._loop()（处理 user.input）
# - Gateway 及所有 Channel（发布 user.input）
# - TitleRuntime / TitleSessionWorker（监听 user.input 生成标题）
# - BusRouter.route_from_public()（路由 user.input 到私有总线）
# - frontend/src/contexts/（WebSocket 事件映射）
# - 所有测试文件
```

---

## 三、标准化后的完整事件流

以下事件流发生在 **PrivateEventBus** 上（双总线架构），所有事件自动回流到 PublicEventBus 供持久化和 Gateway 消费。

### 简单对话

```
user.input                                              ← Gateway → PublicBus → BusRouter → PrivBus
  ↓
agent.step_started                                      ← AgentWorker 发布到 PrivBus，回流到 PublicBus
  ↓
llm.call_requested → llm.call_started → llm.call_result → llm.call_completed
  ↓
agent.step_completed                                    → 回流到 PublicBus → Gateway → 用户
```

### 带工具调用

```
user.input
  ↓
agent.step_started
  ↓
llm.call_requested → llm.call_started → llm.call_result(含tool_calls) → llm.call_completed
  ↓
tool.call_requested → tool.call_started → tool.call_result → tool.call_completed
  ↓  (可能多个并发，均在同一个 PrivateEventBus 上)
llm.call_requested → llm.call_started → llm.call_result(最终响应) → llm.call_completed
  ↓
agent.step_completed
```

### 事件层级说明

```
编排层（两阶段）：agent.step_started ──────────────────→ agent.step_completed
                        ↓ 触发                                ↑ 聚合
执行层（四阶段）：  requested → started → result → completed
                   （适用于 llm.call_* 和 tool.call_*）

所有事件在 PrivateEventBus 上流转，自动回流到 PublicEventBus
```

---

## 四、迁移方案

本项目为单仓库结构，所有前后端代码在同一 repo 中维护，采用一步到位方案。

> 事件标准化与双总线架构可**同步实施**或**先后实施**。如果先做事件标准化，
> 改动集中在事件类型和 Payload；后续做双总线时 Worker 直接使用新事件类型即可。
> 如果同步实施，在拆分 Worker 的同时一并调整事件类型。

### 实施步骤

1. **修改 `events/types.py`**：新增 `TOOL_CALL_RESULT`、`USER_INPUT`、`USER_TURN_CANCEL_REQUESTED`，移除 `TOOL_EXECUTION_START`、`TOOL_EXECUTION_END`、`UI_USER_INPUT`、`UI_TURN_CANCEL_REQUESTED`
2. **修改 ToolRuntime / ToolSessionWorker**：拆分 `completed` 为 `result` + `completed`，移除 `execution_start` / `execution_end` 发布
3. **修改 AgentRuntime / AgentSessionWorker**：监听 `TOOL_CALL_RESULT` 替代 `TOOL_CALL_COMPLETED` 获取工具结果
4. **修改 Gateway 及所有 Channel**：发布 `user.input` 替代 `ui.user_input`
5. **修改前端 WebSocket 事件映射**：同步更新事件类型字符串
6. **修改所有测试文件**：更新事件类型引用
7. **运行 e2e 测试**：验证完整对话链路正常

> 不采用三阶段双发迁移。原因：单仓库项目中所有生产方/消费方一次性修改即可，双发策略
> 适合多仓库/多团队独立发版的场景，在此处只会增加中间状态的维护成本。

---

## 五、验证要点

1. **e2e 测试**：完整对话链路（user.input → agent.step_completed）正常运行
2. **事件持久化**：events 表中新事件类型正确写入，旧事件类型不再出现
3. **前端兼容**：WebSocket 下发的事件类型正确映射
4. **多 Channel**：CLI/TUI/Web 三种接入方式均正常触发 `user.input`
5. **监控验证**：仅订阅 `tool.call_completed`（通过 PublicEventBus 回流）即可获取 tool_name 和 success 摘要
6. **隔离验证**：两个 session 并发时，各自 PrivateEventBus 上的事件类型正确、不串扰
