# 完整对话处理流程

## 概述

本文档以一次完整的用户对话请求为例，详细描述消息从进入系统到响应推送的全过程。涵盖事件流转、状态变迁和模块协作的每一个步骤。

---

## 流程总览

```
用户发送消息
  │
  ▼
┌──────────────────────────────────────────────────────────────┐
│ 1. 用户输入    Channel 接收 → 封装 EventEnvelope → PublicEventBus │
├──────────────────────────────────────────────────────────────┤
│ 2. 事件路由    BusRouter 按 session_id 路由 → PrivateEventBus    │
├──────────────────────────────────────────────────────────────┤
│ 3. Agent 编排  AgentSessionWorker 加载历史 → 构建上下文           │
├──────────────────────────────────────────────────────────────┤
│ 4. LLM 调用   LLMSessionWorker 执行 LLM API 调用               │
├──────────────────────────────────────────────────────────────┤
│ 5. 工具执行    ToolSessionWorker 并行执行工具（可循环多次）        │
├──────────────────────────────────────────────────────────────┤
│ 6. 最终响应    保存结果 → 发布 agent.step_completed              │
├──────────────────────────────────────────────────────────────┤
│ 7. 响应推送    Gateway → Channel → 前端展示                     │
├──────────────────────────────────────────────────────────────┤
│ 8. 事件持久化  EventPersister 全程记录所有事件到 SQLite           │
└──────────────────────────────────────────────────────────────┘
```

---

## 第一步：用户输入

用户通过某个 Channel（如 WebSocket）发送消息，进入系统。

### 详细过程

```
用户在浏览器中输入 "帮我搜索最新的 AI 新闻" 并发送
      │
      ▼
WebSocket 连接将消息传输到服务端
      │
      ▼
WebSocketChannel 接收原始消息
      │
      ▼
封装为 EventEnvelope：
  event_id:   "uuid-001"
  type:       "user.input"
  session_id: "session-abc"
  agent_id:   "default"
  turn_id:    "turn-xyz"        ← 新生成的轮次 ID
  payload:    {"text": "帮我搜索最新的 AI 新闻"}
  source:     "user"
      │
      ▼
通过 Gateway 发布到 PublicEventBus
```

### 关键点

- Channel 负责生成 `turn_id`，标识这是一个新的对话轮次
- `session_id` 与 WebSocket 连接关联，同一个连接的所有消息共享 session_id
- 消息内容放在 `payload.text` 中

---

## 第二步：事件路由

PublicEventBus 广播事件，BusRouter 负责将其路由到正确的 PrivateEventBus。

### 详细过程

```
PublicEventBus 广播 user.input 事件
      │
      ├──► EventPersister 接收（异步写入 SQLite events 表）
      ├──► Gateway 接收（暂无需推送，忽略）
      │
      ▼
BusRouter 接收事件
      │
      ▼
读取 event.session_id = "session-abc"
      │
      ▼
查找是否已存在 PrivateEventBus("session-abc")？
      │
      ├── 已存在 → 直接转发到该 PrivateEventBus
      │
      └── 不存在（新 session）→ 创建流程：
            │
            ├── 创建 PrivateEventBus("session-abc")
            │
            ├── 通过已注册的 factory 创建 Worker：
            │     ├── AgentRuntime.factory → AgentSessionWorker
            │     ├── LLMRuntime.factory   → LLMSessionWorker
            │     └── ToolRuntime.factory  → ToolSessionWorker
            │
            ├── 所有 Worker 开始监听 PrivateEventBus
            │
            └── 转发 user.input 事件到 PrivateEventBus
```

### 关键点

- PrivateEventBus 和 Worker 的创建是**懒加载**的，只有首次收到某 session 的 `user.input` 时才创建
- 创建后的 Worker 作为 asyncio Task 持续运行
- BusRouter 同时更新该 session 的 TTL 计时器

---

## 第三步：Agent 编排

AgentSessionWorker 从 PrivateEventBus 消费 `user.input`，开始编排对话流程。

### 详细过程

```
AgentSessionWorker 消费 user.input 事件
      │
      ▼
创建 TurnState(turn_id="turn-xyz", user_input="帮我搜索最新的 AI 新闻")
      │
      ▼
检查是否为首轮对话（_session_first_turn）？
      │
      ├── 是 → 从 SQLite 加载该 session 的历史消息到内存
      └── 否 → 使用内存中已有的历史
      │
      ▼
通过 ContextBuilder 构建完整上下文：
      │
      ├── 1. 系统提示（system prompt）
      │     └── 包含 Agent 配置的 system_prompt
      │     └── 注入 MEMORY.md 内容（如果存在）
      │     └── 注入 workspace 文件信息
      │
      ├── 2. 历史消息（从内存中获取）
      │     └── [{role: "user", content: "之前的消息"}, ...]
      │
      ├── 3. 当前用户输入
      │     └── {role: "user", content: "帮我搜索最新的 AI 新闻"}
      │
      └── 4. 工具定义（从 ToolRegistry 获取）
            └── [{type: "function", function: {name: "serper_search", ...}}, ...]
      │
      ▼
发布 agent.step_started 事件
  payload: {turn_id: "turn-xyz", user_input: "帮我搜索最新的 AI 新闻"}
      │
      ▼
发布 llm.call_requested 事件
  payload: {
    messages: [系统提示 + 历史 + 当前输入],
    tools: [工具定义列表],
    model: "gpt-4o-mini",
    provider: "openai",
    temperature: 0.7
  }
  trace_id: "llm-call-001"     ← 新生成的 LLM 调用 ID
```

### 关键点

- ContextBuilder 负责组装完整的 messages 列表，包括系统提示、记忆、历史和当前输入
- 工具定义从 ToolRegistry 获取，包含所有已注册工具的 JSON Schema
- `trace_id` 用于关联后续的 `llm.call_result` 事件

---

## 第四步：LLM 调用

LLMSessionWorker 消费 `llm.call_requested`，执行实际的 LLM API 调用。

### 详细过程

```
LLMSessionWorker 消费 llm.call_requested 事件
      │
      ▼
发布 llm.call_started 事件（标记开始）
      │
      ▼
从 payload 提取参数：
  messages: [...]
  tools:    [...]
  model:    "gpt-4o-mini"
  provider: "openai"
      │
      ▼
通过 LLMFactory 获取 provider 实例
  LLMFactory.get_provider("openai") → OpenAIProvider
      │
      ▼
调用 provider.call(model, messages, tools)
  → HTTP 请求到 OpenAI API（或兼容网关）
  → 等待响应...
      │
      ▼
解析 LLM 响应
      │
      ├── 情况 A：LLM 返回 tool_calls
      │   response = {content: null, tool_calls: [{id, type, function: {name, arguments}}]}
      │
      └── 情况 B：LLM 返回文本回复
          response = {content: "这是回复内容", tool_calls: []}
      │
      ▼
发布 llm.call_result 事件
  trace_id: "llm-call-001"     ← 与请求相同的 trace_id
  payload: {content: ..., tool_calls: [...]}
      │
      ▼
发布 llm.call_completed 事件
```

### 关键点

- LLM 调用是异步的，不阻塞事件循环
- provider.call() 内部处理消息归一化（确保 tool_calls 包含 `type: "function"`）
- `trace_id` 与请求事件保持一致，用于 AgentSessionWorker 匹配响应

---

## 第五步：工具执行循环

如果 LLM 返回了 tool_calls，AgentSessionWorker 进入工具执行循环。

### 详细过程

```
AgentSessionWorker 消费 llm.call_result 事件
      │
      ▼
检查 tool_calls：
  tool_calls = [
    {id: "call_abc", function: {name: "serper_search", arguments: '{"query":"最新 AI 新闻"}'}},
    {id: "call_def", function: {name: "serper_search", arguments: '{"query":"AI 2026"}'}}
  ]
      │
      ▼
追加 assistant 消息到 TurnState.messages
设置 pending_tool_calls = {"call_abc", "call_def"}
      │
      ▼
对每个 tool_call 发布 tool.call_requested 事件：
      │
      ├── tool.call_requested (1)
      │   trace_id: "call_abc"
      │   payload: {tool_name: "serper_search", arguments: {query: "最新 AI 新闻"}, tool_call_id: "call_abc"}
      │
      └── tool.call_requested (2)
          trace_id: "call_def"
          payload: {tool_name: "serper_search", arguments: {query: "AI 2026"}, tool_call_id: "call_def"}
      │
      ▼（事件流转到 ToolSessionWorker）

ToolSessionWorker 并行消费 tool.call_requested：
      │
      ├── 工具 1（serper_search）：
      │   ├── 发布 tool.call_started
      │   ├── PathPolicy 权限检查（serper_search 不涉及文件路径，跳过）
      │   ├── 从 ToolRegistry 获取 serper_search 工具
      │   ├── 执行 serper_search(query="最新 AI 新闻")
      │   ├── 结果截断（防止超长输出）
      │   ├── 发布 tool.call_result
      │   │   payload: {result: "搜索结果：1. ...", success: true, tool_call_id: "call_abc"}
      │   └── 发布 tool.call_completed
      │
      └── 工具 2（serper_search）：（并行执行）
          ├── 发布 tool.call_started
          ├── 执行 serper_search(query="AI 2026")
          ├── 发布 tool.call_result
          │   payload: {result: "搜索结果：1. ...", success: true, tool_call_id: "call_def"}
          └── 发布 tool.call_completed

      │
      ▼（结果回流到 AgentSessionWorker）

AgentSessionWorker 收集工具结果：
      │
      ├── 收到 tool.call_result (call_abc)
      │   └── pending_tool_calls = {"call_def"}（移除 call_abc）
      │
      ├── 收到 tool.call_result (call_def)
      │   └── pending_tool_calls = {}（全部完成）
      │
      ▼
组装 tool 消息追加到 messages：
  {role: "tool", tool_call_id: "call_abc", name: "serper_search", content: "搜索结果..."}
  {role: "tool", tool_call_id: "call_def", name: "serper_search", content: "搜索结果..."}
      │
      ▼
再次发布 llm.call_requested（回到第四步）
  messages: [系统提示 + 历史 + 用户输入 + assistant(tool_calls) + tool结果]
  trace_id: "llm-call-002"     ← 新的 LLM 调用 ID
```

### 关键点

- 多个工具调用是**并发执行**的，但结果在 AgentSessionWorker 中统一收集
- `pending_tool_calls` 集合用于跟踪并发工具的完成状态
- 工具结果按 `tool_call_id` 关联回对应的 tool_call
- 结果截断防止工具输出过长导致上下文溢出

---

## 第六步：最终响应

LLM 返回不包含 tool_calls 的 stop 响应，AgentSessionWorker 提取最终回复。

### 详细过程

```
AgentSessionWorker 消费 llm.call_result 事件
      │
      ▼
检查 tool_calls：空（stop 响应）
      │
      ▼
提取 content：
  "根据搜索结果，最新的 AI 新闻包括：
   1. OpenAI 发布了新版本...
   2. Google 推出了..."
      │
      ▼
设置 TurnState.final_response = content
      │
      ▼
追加 assistant 消息到 _session_history
      │
      ▼
持久化到 SQLite：
  ├── 写入 messages 表（本轮所有消息）
  └── 更新 sessions 表的 updated_at
      │
      ▼
发布 agent.step_completed 事件
  payload: {result: "根据搜索结果，最新的 AI 新闻包括：..."}
```

---

## 第七步：响应推送

`agent.step_completed` 事件通过 PublicEventBus 广播，Gateway 负责推送给用户。

### 详细过程

```
PublicEventBus 广播 agent.step_completed 事件
      │
      ▼
Gateway 订阅者接收事件
      │
      ▼
根据 event.session_id = "session-abc" 查找对应的 Channel
      │
      ▼
WebSocketChannel 接收事件
      │
      ▼
将 payload.result 封装为 WebSocket 消息
      │
      ▼
通过 WebSocket 连接推送给前端
      │
      ▼
前端接收并渲染 Agent 的回复
```

---

## 第八步：事件持久化

EventPersister 在整个流程中独立运行，持续将所有事件写入 SQLite。

### 详细过程

```
EventPersister 独立订阅 PublicEventBus
      │
      ▼
接收到的每一个事件：
  user.input
  agent.step_started
  llm.call_requested
  llm.call_started
  llm.call_result
  llm.call_completed
  tool.call_requested (x2)
  tool.call_started (x2)
  tool.call_result (x2)
  tool.call_completed (x2)
  llm.call_requested (第二轮)
  llm.call_started
  llm.call_result
  llm.call_completed
  agent.step_completed
      │
      ▼
逐条写入 SQLite events 表：
  INSERT INTO events (event_id, type, session_id, turn_id, trace_id, payload, ts)
  VALUES (...)
```

### 关键点

- EventPersister 与业务流程**完全独立**，不影响对话处理的延迟
- 所有事件无差别持久化，提供完整的审计日志
- 可用于事件回放、问题排查和性能分析

---

## 完整事件序列

以下是一次带工具调用的对话中，所有事件的完整时序：

| 序号 | 事件类型 | 来源 | 说明 |
|------|----------|------|------|
| 1 | `user.input` | Channel | 用户发送消息 |
| 2 | `agent.step_started` | AgentSessionWorker | 开始处理 |
| 3 | `llm.call_requested` | AgentSessionWorker | 请求第一轮 LLM 调用 |
| 4 | `llm.call_started` | LLMSessionWorker | LLM 调用开始 |
| 5 | `llm.call_result` | LLMSessionWorker | LLM 返回 tool_calls |
| 6 | `llm.call_completed` | LLMSessionWorker | LLM 调用流程结束 |
| 7 | `tool.call_requested` (1) | AgentSessionWorker | 请求执行工具 1 |
| 8 | `tool.call_requested` (2) | AgentSessionWorker | 请求执行工具 2 |
| 9 | `tool.call_started` (1) | ToolSessionWorker | 工具 1 开始执行 |
| 10 | `tool.call_started` (2) | ToolSessionWorker | 工具 2 开始执行 |
| 11 | `tool.call_result` (1) | ToolSessionWorker | 工具 1 执行完成 |
| 12 | `tool.call_result` (2) | ToolSessionWorker | 工具 2 执行完成 |
| 13 | `tool.call_completed` (1) | ToolSessionWorker | 工具 1 流程结束 |
| 14 | `tool.call_completed` (2) | ToolSessionWorker | 工具 2 流程结束 |
| 15 | `llm.call_requested` | AgentSessionWorker | 请求第二轮 LLM 调用（携带工具结果） |
| 16 | `llm.call_started` | LLMSessionWorker | LLM 调用开始 |
| 17 | `llm.call_result` | LLMSessionWorker | LLM 返回最终文本（stop） |
| 18 | `llm.call_completed` | LLMSessionWorker | LLM 调用流程结束 |
| 19 | `agent.step_completed` | AgentSessionWorker | 对话轮次完成，推送响应 |

> 注意：工具执行是并发的，因此 9-14 的顺序可能因实际执行速度而变化。
