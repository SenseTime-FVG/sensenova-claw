# 事件系统概述

## 核心设计理念

事件驱动是 AgentOS 的核心设计模式。系统中所有模块间的通信都通过事件完成，**没有直接方法调用**。每个模块只需关心自己订阅的事件类型和发布的事件类型，无需了解其他模块的实现细节。

这种设计带来以下优势：

- **松耦合**：新增模块只需订阅/发布事件，无需修改已有代码
- **可测试**：注入事件、断言输出事件，即可完成单元测试
- **可审计**：所有事件自动持久化，完整记录系统行为
- **可扩展**：插件可以通过订阅事件来扩展系统能力

---

## 事件类型分类

### 用户事件

| 事件类型 | 说明 | 来源 |
|----------|------|------|
| `user.input` | 用户发送消息 | Channel |
| `user.turn_cancel_requested` | 用户请求取消当前轮次 | Channel |

### Agent 编排事件

| 事件类型 | 说明 | 来源 |
|----------|------|------|
| `agent.step_started` | Agent 开始处理一个步骤 | AgentSessionWorker |
| `agent.step_completed` | Agent 完成步骤，包含最终回复 | AgentSessionWorker |

### LLM 调用事件

| 事件类型 | 说明 | 来源 |
|----------|------|------|
| `llm.call_requested` | 请求发起 LLM 调用 | AgentSessionWorker |
| `llm.call_started` | LLM 调用开始执行 | LLMSessionWorker |
| `llm.call_result` | LLM 返回结果（content 或 tool_calls） | LLMSessionWorker |
| `llm.call_completed` | LLM 调用完整流程结束 | LLMSessionWorker |

### 工具执行事件

| 事件类型 | 说明 | 来源 |
|----------|------|------|
| `tool.call_requested` | 请求执行工具 | AgentSessionWorker |
| `tool.call_started` | 工具开始执行 | ToolSessionWorker |
| `tool.call_result` | 工具执行返回结果 | ToolSessionWorker |
| `tool.call_completed` | 工具调用完整流程结束 | ToolSessionWorker |

### 工具权限事件

| 事件类型 | 说明 | 来源 |
|----------|------|------|
| `tool.confirmation_requested` | 工具执行需要用户确认（如危险操作） | ToolSessionWorker |
| `tool.confirmation_response` | 用户对确认请求的回应 | Channel |

### 错误事件

| 事件类型 | 说明 | 来源 |
|----------|------|------|
| `error.raised` | 系统错误 | 任何模块 |

### 定时任务事件

| 事件类型 | 说明 | 来源 |
|----------|------|------|
| `cron.job_added` | 新增定时任务 | CronRuntime |
| `cron.job_updated` | 更新定时任务 | CronRuntime |
| `cron.job_removed` | 删除定时任务 | CronRuntime |
| `cron.job_started` | 定时任务开始执行 | CronRuntime |
| `cron.job_finished` | 定时任务执行完成 | CronRuntime |
| `cron.system_event` | 定时任务系统事件 | CronRuntime |
| `cron.delivery_requested` | 定时任务结果投递请求 | CronRuntime |

### 心跳事件

| 事件类型 | 说明 | 来源 |
|----------|------|------|
| `heartbeat.wake_requested` | 请求唤醒心跳检测 | 系统 |
| `heartbeat.check_started` | 心跳检测开始 | HeartbeatRuntime |
| `heartbeat.completed` | 心跳检测完成 | HeartbeatRuntime |

---

## 事件流转机制

事件在系统中的流转遵循固定路径：

```
模块/Worker 产生事件
       │
       ▼
  PublicEventBus（全局广播）
       │
       ├──► EventPersister（持久化到 SQLite）
       ├──► Gateway（推送到 Channel/前端）
       │
       ▼
  BusRouter（按 session_id 路由）
       │
       ▼
  PrivateEventBus（会话级）
       │
       ▼
  Worker 消费事件 → 处理 → 产生新事件
       │
       └──► 回流到 PublicEventBus（循环）
```

### 关键规则

1. **所有事件必须经过 PublicEventBus**：即使是同一个 session 内 Worker 之间的通信，也要经过 Public → BusRouter → Private 的完整链路
2. **事件不可修改**：一旦发布，事件信封的内容不可变
3. **事件有序性**：同一个 PrivateEventBus 内的事件按发布顺序消费
4. **session 隔离**：不同 session 的事件通过 PrivateEventBus 物理隔离，互不干扰

---

## 典型事件链路示例

### 普通文本对话（无工具调用）

```
user.input
  → agent.step_started
    → llm.call_requested
      → llm.call_started
      → llm.call_result        ← content="你好！", tool_calls=[]
      → llm.call_completed
  → agent.step_completed        ← result="你好！"
```

### 带工具调用的对话

```
user.input
  → agent.step_started
    → llm.call_requested
      → llm.call_started
      → llm.call_result        ← tool_calls=[{name:"bash_command", args:{...}}]
      → llm.call_completed
    → tool.call_requested       ← tool_name="bash_command"
      → tool.call_started
      → tool.call_result        ← result="命令输出..."
      → tool.call_completed
    → llm.call_requested        ← messages 包含工具结果
      → llm.call_started
      → llm.call_result        ← content="根据执行结果..."
      → llm.call_completed
  → agent.step_completed        ← result="根据执行结果..."
```

### 多工具并发调用

```
user.input
  → agent.step_started
    → llm.call_requested
      → llm.call_result        ← tool_calls=[{serper_search}, {serper_search}, {fetch_url}]
    → tool.call_requested (1)   ← serper_search
    → tool.call_requested (2)   ← serper_search
    → tool.call_requested (3)   ← fetch_url
      → tool.call_result (1)   ← 并发执行
      → tool.call_result (3)
      → tool.call_result (2)   ← 结果到达顺序不确定
    → llm.call_requested        ← 收集全部工具结果后发起
      → llm.call_result
  → agent.step_completed
```
