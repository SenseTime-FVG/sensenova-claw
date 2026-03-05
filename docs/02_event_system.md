# 事件系统设计

## EventEnvelope 数据结构

事件封装是系统中所有消息传递的标准格式，确保事件的可追踪性和一致性。

### 字段定义

```python
class EventEnvelope:
    event_id: str          # 全局唯一事件ID (UUID)
    type: str              # 事件类型 (如 "llm.call_completed")
    ts: float              # 时间戳 (Unix timestamp)
    session_id: str        # 会话ID
    agent_id: str          # Agent ID (多Agent场景)
    turn_id: str           # 对话轮次ID
    step_id: str           # 步骤ID (可选但推荐)
    trace_id: str          # 追踪ID，用于关联请求和响应
    payload: dict          # 事件负载数据
    source: str            # 事件来源 (ui/agent/llm/tool/system)
```

### trace_id 的作用

`trace_id` 是关联请求和响应的关键字段，例如：
- `llm_call_id`: 关联 `llm.call_requested` 和 `llm.call_completed`
- `tool_call_id`: 关联 `tool.call_requested` 和 `tool.call_completed`

## 事件类型定义

### 1. UI 事件

#### ui.user_input
用户在界面输入消息时触发。

**Payload 结构**:
```python
{
    "content": str,           # 用户输入内容
    "attachments": list,      # 附件列表 (可选)
    "context_files": list     # 引用的文件列表 (可选)
}
```

#### ui.turn_cancel_requested
用户请求取消当前对话轮次。

**Payload 结构**:
```python
{
    "reason": str  # 取消原因 (可选)
}
```

### 2. Agent 事件

#### agent.step_started
Agent 开始处理一个步骤。

**Payload 结构**:
```python
{
    "step_type": str,      # 步骤类型 (llm_call/tool_call/final)
    "description": str     # 步骤描述
}
```

#### agent.step_completed
Agent 完成一个步骤。

**Payload 结构**:
```python
{
    "step_type": str,
    "result": dict,        # 步骤结果
    "next_action": str     # 下一步动作 (continue/end)
}
```

#### user.input
Agent 接收到的用户输入（内部事件）。

**Payload 结构**:
```python
{
    "content": str,
    "metadata": dict
}
```

### 3. LLM 事件

#### llm.call_requested
请求调用 LLM。

**Payload 结构**:
```python
{
    "llm_call_id": str,       # 本次调用的唯一ID
    "model": str,             # 模型名称
    "messages": list,         # 消息列表
    "tools": list,            # 可用工具列表 (可选)
    "temperature": float,     # 温度参数 (可选)
    "max_tokens": int         # 最大token数 (可选)
}
```

#### llm.call_started
LLM 开始处理请求。

**Payload 结构**:
```python
{
    "llm_call_id": str,
    "model": str
}
```

#### llm.call_completed
LLM 调用完成。

**Payload 结构**:
```python
{
    "llm_call_id": str,
    "response": dict,         # LLM 响应内容
    "usage": dict,            # Token 使用情况
    "finish_reason": str      # 结束原因 (stop/tool_calls/length)
}
```

### 4. Tool 事件

#### tool.call_requested
请求执行工具。

**Payload 结构**:
```python
{
    "tool_call_id": str,      # 工具调用ID
    "tool_name": str,         # 工具名称
    "arguments": dict         # 工具参数
}
```

#### tool.call_started
工具开始执行。

**Payload 结构**:
```python
{
    "tool_call_id": str,
    "tool_name": str
}
```

#### tool.call_completed
工具执行完成。

**Payload 结构**:
```python
{
    "tool_call_id": str,
    "tool_name": str,
    "result": any,            # 工具执行结果
    "success": bool,          # 是否成功
    "error": str              # 错误信息 (如果失败)
}
```

#### tool.execution_start
工具内部执行开始（细粒度追踪）。

#### tool.execution_end
工具内部执行结束（细粒度追踪）。

### 5. 错误事件

#### error.raised
系统发生错误。

**Payload 结构**:
```python
{
    "error_type": str,        # 错误类型
    "error_message": str,     # 错误消息
    "stack_trace": str,       # 堆栈追踪
    "context": dict           # 错误上下文
}
```

## 事件流转示例

### 简单对话流程

```
ui.user_input
    ↓
agent.step_started
    ↓
llm.call_requested
    ↓
llm.call_started
    ↓
llm.call_completed (finish_reason: stop)
    ↓
agent.step_completed
```

### 带工具调用的流程

```
ui.user_input
    ↓
agent.step_started
    ↓
llm.call_requested
    ↓
llm.call_started
    ↓
llm.call_completed (finish_reason: tool_calls)
    ↓
tool.call_requested (可能多个)
    ↓
tool.call_started
    ↓
tool.execution_start
    ↓
tool.execution_end
    ↓
tool.call_completed
    ↓
llm.call_requested (带工具结果)
    ↓
llm.call_completed (finish_reason: stop)
    ↓
agent.step_completed
```

## 事件总线实现要点

### Public Bus
- 使用 asyncio.Queue 实现
- 支持多订阅者模式
- 事件持久化到数据库

### Private Bus
- 每个 Agent 实例独立的队列
- 通过 Bus Router 接收过滤后的事件
- 保证会话隔离

### Bus Router
- 监听 Public Bus
- 根据 `session_id` 路由事件
- 维护 session 到 Agent 的映射关系

## 事件持久化

所有事件都会存储到 SQLite 的 `events` 表中，用于：
- 会话回放
- 调试追踪
- 性能分析
- 审计日志
