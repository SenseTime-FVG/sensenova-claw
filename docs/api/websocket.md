# WebSocket 协议

AgentOS 通过 WebSocket 实现前端与后端的实时双向通信。所有对话交互、事件推送均通过 WebSocket 完成。

---

## 连接地址

```
ws://localhost:8000/ws
```

连接后，客户端通过发送 JSON 消息与服务端交互，服务端通过推送事件消息通知客户端状态变化。

---

## 客户端发送消息格式

所有客户端消息均为 JSON 格式，包含 `type` 字段标识消息类型。

### 创建会话

首次连接后，需要先创建会话才能开始对话。

```json
{
  "type": "create_session",
  "payload": {
    "agent_id": "default",
    "meta": {}
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | 固定为 `"create_session"` |
| `payload.agent_id` | string | 使用的 Agent ID，默认 `"default"` |
| `payload.meta` | object | 自定义元数据 |

服务端响应：

```json
{
  "type": "session_created",
  "session_id": "sess_abc123def456",
  "payload": {
    "created_at": 1710400000.0
  },
  "timestamp": 1710400000.0
}
```

### 列出会话

获取历史会话列表。

```json
{
  "type": "list_sessions",
  "payload": {
    "limit": 50
  }
}
```

服务端响应：

```json
{
  "type": "sessions_list",
  "payload": {
    "sessions": [
      {
        "session_id": "sess_abc123",
        "status": "active",
        "created_at": 1710400000.0,
        "last_active": 1710401000.0
      }
    ]
  },
  "timestamp": 1710400000.0
}
```

### 加载已有会话

恢复历史会话，服务端会返回该会话的所有事件用于回放。

```json
{
  "type": "load_session",
  "payload": {
    "session_id": "sess_abc123"
  }
}
```

服务端响应：

```json
{
  "type": "session_loaded",
  "session_id": "sess_abc123",
  "payload": {
    "events": [...]
  },
  "timestamp": 1710400000.0
}
```

### 发送用户消息

在已创建/加载的会话中发送用户输入，触发 Agent 处理流程。

```json
{
  "type": "user_input",
  "session_id": "sess_abc123",
  "payload": {
    "content": "帮我搜索一下 Python 最新版本"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | 固定为 `"user_input"` |
| `session_id` | string | 当前会话 ID |
| `payload.content` | string | 用户输入的文本内容 |

### 取消当前轮次

中断正在进行的 Agent 处理。

```json
{
  "type": "cancel_turn",
  "session_id": "sess_abc123"
}
```

### 工具确认响应

当高风险工具需要用户确认时，发送确认或拒绝。

```json
{
  "type": "tool_confirmation_response",
  "session_id": "sess_abc123",
  "payload": {
    "tool_call_id": "call_xxx",
    "approved": true
  }
}
```

---

## 服务端推送消息格式

服务端将内部事件（`EventEnvelope`）映射为前端友好的消息格式后推送。所有推送消息包含以下公共字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | 消息类型 |
| `session_id` | string | 所属会话 ID |
| `payload` | object | 消息载荷 |
| `timestamp` | float | 时间戳（Unix 秒） |

### `agent_thinking`

Agent 开始处理或正在调用模型。收到此消息时，前端应显示加载动画。

**触发条件**：内部事件 `agent.step_started` 或 `llm.call_requested`

```json
{
  "type": "agent_thinking",
  "session_id": "sess_abc123",
  "payload": {
    "step_type": "llm_call",
    "description": "正在调用模型..."
  },
  "timestamp": 1710400001.0
}
```

### `tool_execution`

工具开始执行。前端应显示工具调用卡片，展示工具名和参数。

**触发条件**：内部事件 `tool.call_requested`

```json
{
  "type": "tool_execution",
  "session_id": "sess_abc123",
  "payload": {
    "tool_call_id": "call_abc123",
    "tool_name": "serper_search",
    "status": "running",
    "arguments": {
      "query": "Python latest version"
    }
  },
  "timestamp": 1710400002.0
}
```

### `tool_result`

工具执行完成，返回结果。前端应更新工具调用卡片的状态和结果。

**触发条件**：内部事件 `tool.call_result`

```json
{
  "type": "tool_result",
  "session_id": "sess_abc123",
  "payload": {
    "tool_call_id": "call_abc123",
    "tool_name": "serper_search",
    "result": "Python 3.13 是最新稳定版...",
    "success": true,
    "error": ""
  },
  "timestamp": 1710400003.0
}
```

### `tool_confirmation_requested`

高风险工具需要用户确认才能执行。前端应弹出确认对话框。

**触发条件**：内部事件 `tool.confirmation_requested`

```json
{
  "type": "tool_confirmation_requested",
  "session_id": "sess_abc123",
  "payload": {
    "tool_call_id": "call_abc123",
    "tool_name": "bash_command",
    "arguments": {
      "command": "rm -rf /tmp/old_data"
    },
    "risk_level": "high"
  },
  "timestamp": 1710400002.5
}
```

### `turn_completed`

Agent 完成本轮处理，返回最终回复文本。前端应显示助手消息气泡。

**触发条件**：内部事件 `agent.step_completed`

```json
{
  "type": "turn_completed",
  "session_id": "sess_abc123",
  "payload": {
    "turn_id": "turn_001",
    "final_response": "根据搜索结果，Python 最新稳定版本是 3.13..."
  },
  "timestamp": 1710400005.0
}
```

### `error`

处理过程中发生错误。前端应显示错误提示。

**触发条件**：内部事件 `error.raised`

```json
{
  "type": "error",
  "session_id": "sess_abc123",
  "payload": {
    "error_type": "LLMCallError",
    "message": "API 调用失败：rate limit exceeded",
    "details": {
      "provider": "openai",
      "status_code": 429
    }
  },
  "timestamp": 1710400006.0
}
```

### `title_updated`

会话标题自动更新。前端应更新侧边栏中的会话标题。

**触发条件**：内部事件 `agent.update_title_completed`

```json
{
  "type": "title_updated",
  "session_id": "sess_abc123",
  "payload": {
    "title": "Python 版本查询",
    "success": true
  },
  "timestamp": 1710400007.0
}
```

### `notification`

来自定时任务的通知消息。此类消息会广播到所有已连接的客户端（不按 session 过滤）。

**触发条件**：内部事件 `cron.delivery_requested`

```json
{
  "type": "notification",
  "session_id": "sess_abc123",
  "payload": {
    "text": "每日摘要已生成",
    "source": "cron",
    "job_id": "job_daily_summary",
    "job_name": "每日摘要"
  },
  "timestamp": 1710400008.0
}
```

---

## 内部事件类型参考

以下是系统内部 `EventEnvelope` 使用的事件类型常量，供开发者参考：

| 事件类型 | 说明 |
|----------|------|
| `user.input` | 用户输入 |
| `user.turn_cancel_requested` | 用户请求取消当前轮次 |
| `agent.step_started` | Agent 开始处理 |
| `agent.step_completed` | Agent 完成处理 |
| `llm.call_requested` | LLM 调用请求 |
| `llm.call_started` | LLM 调用开始 |
| `llm.call_result` | LLM 调用结果 |
| `llm.call_completed` | LLM 调用完成 |
| `tool.call_requested` | 工具调用请求 |
| `tool.call_started` | 工具调用开始 |
| `tool.call_result` | 工具调用结果 |
| `tool.call_completed` | 工具调用完成 |
| `tool.confirmation_requested` | 工具确认请求（高风险） |
| `tool.confirmation_response` | 工具确认响应 |
| `error.raised` | 错误事件 |
| `agent.delegate_requested` | Agent 委托请求 |
| `agent.delegate_completed` | Agent 委托完成 |

---

## EventEnvelope 数据结构

所有内部事件均封装为 `EventEnvelope`：

```python
class EventEnvelope(BaseModel):
    event_id: str        # UUID，事件唯一标识
    type: str            # 事件类型（见上表）
    ts: float            # 时间戳（Unix 秒）
    session_id: str      # 会话 ID
    agent_id: str        # Agent ID，默认 "default"
    turn_id: str | None  # 对话轮次 ID
    step_id: str | None  # 步骤 ID
    trace_id: str | None # 追踪 ID（关联请求/响应）
    payload: dict        # 事件载荷数据
    source: str          # 事件来源，默认 "system"
```

---

## 典型事件流

一次完整的用户对话交互，事件流如下：

```
客户端                          服务端
  |                               |
  |--- create_session ----------->|
  |<-- session_created -----------|
  |                               |
  |--- user_input --------------->|
  |<-- agent_thinking ------------|  (agent.step_started)
  |<-- agent_thinking ------------|  (llm.call_requested)
  |                               |  ... LLM 处理中 ...
  |<-- tool_execution ------------|  (tool.call_requested, 如有工具调用)
  |<-- tool_result ---------------|  (tool.call_result)
  |                               |  ... 可能有多轮 LLM + Tool ...
  |<-- turn_completed ------------|  (agent.step_completed)
  |<-- title_updated -------------|  (首轮对话后自动生成标题)
  |                               |
```

---

## 前端事件处理建议

| 收到消息类型 | 建议处理 |
|-------------|---------|
| `agent_thinking` | 显示加载动画 / "思考中..." 提示 |
| `tool_execution` | 显示工具调用卡片（工具名 + 参数） |
| `tool_result` | 更新工具卡片状态（成功/失败 + 结果摘要） |
| `tool_confirmation_requested` | 弹出确认对话框，等待用户操作 |
| `turn_completed` | 显示助手消息气泡，隐藏加载动画 |
| `error` | 显示错误提示，隐藏加载动画 |
| `title_updated` | 更新侧边栏会话标题 |
| `notification` | 显示通知 toast |
