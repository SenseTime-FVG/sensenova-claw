# Runtime 与 Worker 机制

## 概述

AgentOS 采用 **Runtime-Worker 二层设计**：Runtime 是全局单例，负责管理配置和资源；Worker 是每 session 一个实例，负责实际的事件处理逻辑。

```
Runtime（全局单例）
  │
  ├── 持有共享资源（Registry、Factory、Store）
  ├── 向 BusRouter 注册 Worker factory
  │
  └── Worker factory
        │
        └── 每 session 创建一个 Worker 实例
              │
              ├── 订阅 PrivateEventBus
              ├── 消费并处理事件
              └── 产生新事件 → 回流到 PublicEventBus
```

---

## Runtime 层（全局单例）

### AgentRuntime

对话流程编排的 Runtime，管理所有 `AgentSessionWorker` 实例。

| 持有资源 | 用途 |
|----------|------|
| `ContextBuilder` | 构建发送给 LLM 的完整消息列表 |
| `ToolRegistry` | 获取可用工具定义 |
| `MemoryManager` | 读写 MEMORY.md |
| `SessionStateStore` | 内存状态管理 |
| `AgentRegistry` | 获取 Agent 配置 |
| `Repository` | SQLite 数据持久化 |

### LLMRuntime

LLM 调用管理的 Runtime，管理所有 `LLMSessionWorker` 实例。

| 持有资源 | 用途 |
|----------|------|
| `LLMFactory` | 根据 provider 配置创建对应的 LLM 提供商实例 |

### ToolRuntime

工具执行的 Runtime，管理所有 `ToolSessionWorker` 实例。

| 持有资源 | 用途 |
|----------|------|
| `ToolRegistry` | 查找并执行工具 |
| `PathPolicy` | 文件路径安全策略检查 |

### TitleRuntime

自动生成会话标题的 Runtime。与前三者不同，TitleRuntime 直接订阅 PublicEventBus，不使用 Worker 模式。

- 监听 `agent.step_completed` 事件
- 提取首轮对话的用户输入和 Agent 回复
- 调用 LLM 生成简短的会话标题
- 将标题写入 SQLite

### CronRuntime

定时任务调度的 Runtime。

- 管理 cron 任务的增删改查
- 按 cron 表达式定时触发任务
- 发布定时任务相关事件

### HeartbeatRuntime

心跳检测的 Runtime。

- 定期检查系统状态
- 检查活跃会话的健康状况
- 发布心跳相关事件

---

## Worker 层（每 session 一个实例）

### AgentSessionWorker

**对话编排的核心**，负责一个 session 内的完整对话流程。

- **监听事件**：`user.input`、`llm.call_result`、`tool.call_result`、`user.turn_cancel_requested`
- **发布事件**：`agent.step_started`、`llm.call_requested`、`tool.call_requested`、`agent.step_completed`

### LLMSessionWorker

负责执行 LLM 调用。

- **监听事件**：`llm.call_requested`
- **发布事件**：`llm.call_started`、`llm.call_result`、`llm.call_completed`
- **执行逻辑**：从事件 payload 提取 messages、tools、model、provider → 通过 LLMFactory 获取 provider 实例 → 调用 `provider.call()` → 发布结果

### ToolSessionWorker

负责执行工具调用。

- **监听事件**：`tool.call_requested`、`tool.confirmation_response`
- **发布事件**：`tool.call_started`、`tool.call_result`、`tool.call_completed`、`tool.confirmation_requested`
- **执行逻辑**：从事件 payload 提取 tool_name 和 arguments → PathPolicy 权限检查 → 从 ToolRegistry 获取工具 → 执行 → 结果截断（防止超长输出） → 发布结果

### Worker 生命周期

Worker 的生命周期与 PrivateEventBus 绑定：

```
BusRouter 检测到新 session
  │
  ▼
创建 PrivateEventBus
  │
  ▼
通过各 Runtime 的 factory 创建 Worker
  │
  ▼
Worker 开始监听 PrivateEventBus（asyncio Task）
  │
  ▼
... 持续处理事件 ...
  │
  ▼
PrivateEventBus TTL 过期
  │
  ▼
BusRouter 回收 → 取消 Worker Task → 关闭 PrivateEventBus
```

---

## AgentSessionWorker 核心循环

AgentSessionWorker 是整个系统中最复杂的 Worker，下面详细描述其核心循环。

### 处理流程

```
收到 user.input 事件
      │
      ▼
  ┌─── 步骤 1：加载历史 ───┐
  │ 首轮对话？              │
  │   是 → 从 SQLite 加载   │
  │        会话历史消息      │
  │   否 → 使用内存中的历史  │
  └────────┬───────────────┘
           │
           ▼
  ┌─── 步骤 2：构建上下文 ──┐
  │ 注入 MEMORY.md 内容      │
  │ 注入 workspace 文件信息   │
  │ 注入 Agent 配置           │
  │ 通过 ContextBuilder 构建  │
  │ 完整消息列表              │
  └────────┬────────────────┘
           │
           ▼
  发布 agent.step_started
           │
           ▼
  ┌─── 步骤 3：LLM 调用循环 ─────────────────────────────┐
  │                                                        │
  │  发布 llm.call_requested                               │
  │  （携带 messages, tools, model, provider, temperature） │
  │         │                                              │
  │         ▼                                              │
  │  等待 llm.call_result                                  │
  │         │                                              │
  │         ▼                                              │
  │  检查 tool_calls                                       │
  │         │                                              │
  │    ┌────┴────┐                                         │
  │    │         │                                         │
  │ 有 tool_calls   无 tool_calls（stop）                    │
  │    │              │                                    │
  │    ▼              ▼                                    │
  │ 步骤 4        步骤 5                                    │
  │                                                        │
  └────────────────────────────────────────────────────────┘

  ┌─── 步骤 4：工具调用 ──────────────────────┐
  │                                            │
  │  对每个 tool_call：                         │
  │    记录到 pending_tool_calls               │
  │    发布 tool.call_requested                │
  │                                            │
  │  等待所有 tool.call_result                  │
  │  （通过 pending_tool_calls 跟踪完成状态）    │
  │                                            │
  │  收集所有工具结果                            │
  │  追加 tool 消息到消息历史                    │
  │                                            │
  │  回到步骤 3（再次发起 LLM 调用）             │
  └────────────────────────────────────────────┘

  ┌─── 步骤 5：完成响应 ──┐
  │                        │
  │  提取 LLM 的 content   │
  │  保存到 SQLite         │
  │  更新 SessionStateStore│
  │  发布 agent.step_completed │
  └────────────────────────┘
```

### 上下文构建详情

ContextBuilder 构建的消息列表结构如下：

```python
messages = [
    # 1. 系统提示
    {"role": "system", "content": "你是一个有用的AI助手...\n\n[MEMORY.md 内容]\n\n[workspace 信息]"},

    # 2. 历史消息（从 SQLite 加载或内存中）
    {"role": "user", "content": "之前的用户消息"},
    {"role": "assistant", "content": "之前的助手回复"},
    ...

    # 3. 当前轮次消息
    {"role": "user", "content": "当前用户输入"},

    # 如果是工具调用循环中：
    {"role": "assistant", "content": null, "tool_calls": [...]},
    {"role": "tool", "tool_call_id": "call_xxx", "name": "bash_command", "content": "工具结果"},
    ...
]
```

### 并发工具调用

当 LLM 一次返回多个 tool_calls 时，AgentSessionWorker 会：

1. 为每个 tool_call 发布独立的 `tool.call_requested` 事件
2. 将所有 tool_call_id 加入 `pending_tool_calls` 集合
3. 每收到一个 `tool.call_result`，从 `pending_tool_calls` 中移除对应 ID
4. 当 `pending_tool_calls` 为空时，表示所有工具执行完毕
5. 按顺序组装所有工具结果，发起下一轮 LLM 调用

工具执行是并发的（由 ToolSessionWorker 并行处理），但结果收集在 AgentSessionWorker 中统一协调。
