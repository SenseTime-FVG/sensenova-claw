# 事件信封 EventEnvelope

## 概述

`EventEnvelope` 是 AgentOS 中最核心的数据结构。系统中所有的通信都通过 EventEnvelope 进行，它封装了事件的完整元信息和业务数据。

---

## 字段定义

```python
class EventEnvelope:
    event_id: str         # UUID，全局唯一标识
    type: str             # 事件类型，如 "user.input", "llm.call_completed"
    ts: float             # 时间戳（Unix timestamp）
    session_id: str       # 会话 ID，用于会话隔离
    agent_id: str         # Agent ID，"default" 或自定义 Agent ID
    turn_id: str | None   # 对话轮次 ID
    step_id: str | None   # 步骤 ID（turn 内的步骤）
    trace_id: str | None  # 关联 ID（如 llm_call_id, tool_call_id）
    payload: dict         # 事件数据，不同事件类型有不同结构
    source: str           # 来源标识
```

---

## 字段详细说明

### event_id

- 格式：UUID v4 字符串
- 用途：全局唯一标识一个事件，用于去重和审计追踪
- 生成时机：事件创建时自动生成

### type

- 格式：`{领域}.{动作}` 的点分命名
- 示例：`user.input`、`llm.call_requested`、`tool.call_result`、`agent.step_completed`
- 用途：Worker 通过 type 过滤自己关心的事件

### ts

- 格式：Unix 时间戳（浮点数，精确到微秒）
- 用途：事件排序、性能分析、超时检测

### session_id

- 格式：UUID v4 字符串
- 用途：**会话隔离的核心标识**
- 作用机制：
  - BusRouter 根据 `session_id` 将事件路由到对应的 PrivateEventBus
  - 不同 session 的事件物理隔离在不同的 PrivateEventBus 中
  - 所有 Worker 实例与 session_id 一一对应
  - SQLite 存储按 session_id 组织数据

### agent_id

- 格式：字符串，默认为 `"default"`
- 用途：多 Agent 场景下标识是哪个 Agent 处理此事件
- 在 AgentRegistry 中查找对应的 AgentConfig

### turn_id

- 格式：UUID v4 字符串，可为 `None`
- 用途：标识一次完整的用户对话轮次（从 `user.input` 到 `agent.step_completed`）
- 在 `user.input` 事件中生成，后续同一轮次的所有事件共享此 ID

### step_id

- 格式：UUID v4 字符串，可为 `None`
- 用途：标识 turn 内的一个处理步骤
- 一个 turn 可能包含多个 step（如多轮工具调用循环）

### trace_id

- 格式：字符串，可为 `None`
- 用途：**关联请求和响应事件**
- 示例：
  - `llm.call_requested` 和 `llm.call_result` 共享同一个 `trace_id`（即 `llm_call_id`）
  - `tool.call_requested` 和 `tool.call_result` 共享同一个 `trace_id`（即 `tool_call_id`）
- 用于跟踪异步请求-响应对

### payload

- 格式：Python 字典
- 用途：携带事件的具体业务数据
- 结构因事件类型而异（详见下方 payload 结构说明）

### source

- 格式：字符串枚举
- 可选值：`"user"`, `"agent"`, `"llm"`, `"tool"`, `"system"`, `"heartbeat"`
- 用途：标识事件的产生来源，便于日志和调试

---

## payload 结构说明

不同事件类型的 payload 包含不同的数据结构。以下是各主要事件类型的 payload 示例。

### user.input

```python
{
    "text": "帮我搜索一下最新的 AI 新闻"
}
```

### llm.call_requested

```python
{
    "messages": [
        {"role": "system", "content": "你是一个有用的AI助手..."},
        {"role": "user", "content": "帮我搜索一下最新的 AI 新闻"}
    ],
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "serper_search",
                "description": "搜索网络信息",
                "parameters": {"type": "object", "properties": {...}}
            }
        }
    ],
    "model": "gpt-4o-mini",
    "provider": "openai",
    "temperature": 0.7
}
```

### llm.call_result

LLM 返回文本回复时：

```python
{
    "content": "根据搜索结果，最新的 AI 新闻包括...",
    "tool_calls": []
}
```

LLM 请求调用工具时：

```python
{
    "content": null,
    "tool_calls": [
        {
            "id": "call_abc123",
            "type": "function",
            "function": {
                "name": "serper_search",
                "arguments": "{\"query\": \"最新 AI 新闻 2026\"}"
            }
        }
    ]
}
```

### tool.call_requested

```python
{
    "tool_name": "serper_search",
    "arguments": {
        "query": "最新 AI 新闻 2026"
    },
    "tool_call_id": "call_abc123"
}
```

### tool.call_result

```python
{
    "result": "搜索结果：1. OpenAI 发布了...",
    "success": true,
    "tool_call_id": "call_abc123"
}
```

工具执行失败时：

```python
{
    "result": "Error: API 请求超时",
    "success": false,
    "tool_call_id": "call_abc123"
}
```

### agent.step_started

```python
{
    "turn_id": "uuid-xxx",
    "user_input": "帮我搜索一下最新的 AI 新闻"
}
```

### agent.step_completed

```python
{
    "result": "根据搜索结果，最新的 AI 新闻包括..."
}
```

### error.raised

```python
{
    "error_type": "LLMCallError",
    "message": "OpenAI API 返回 429: Rate limit exceeded",
    "traceback": "..."
}
```

---

## 事件创建示例

使用 EventPublisher 创建和发布事件的伪代码：

```python
# 创建 user.input 事件
envelope = EventEnvelope(
    event_id=str(uuid4()),
    type="user.input",
    ts=time.time(),
    session_id="session-abc",
    agent_id="default",
    turn_id=str(uuid4()),
    step_id=None,
    trace_id=None,
    payload={"text": "你好"},
    source="user"
)

# 发布到 PublicEventBus
await public_event_bus.publish(envelope)
```

---

## 设计原则

1. **不可变性**：EventEnvelope 一旦创建，其字段值不应被修改
2. **自描述性**：通过 type、source、trace_id 等字段，一个事件自身就包含了完整的上下文信息
3. **扁平化**：核心元信息在顶层字段中，业务数据统一放在 payload 中
4. **可序列化**：所有字段都是基本类型或字典，可直接 JSON 序列化用于持久化和传输
