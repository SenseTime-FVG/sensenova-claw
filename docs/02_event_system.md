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
    turn_id: str           # 对话轮次ID
    trace_id: str          # 追踪ID，用于关联请求和响应
    payload: dict          # 事件负载数据
    source: str            # 事件来源 (ui/agent/llm/tool/system/title)
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
    "final_response": str,     # 最终响应内容
    "turn_id": str             # 对话轮次ID
}
```

### 3. LLM 事件

#### llm.call_requested
请求调用 LLM。

**Payload 结构**:
```python
{
    "llm_call_id": str,       # 本次调用的唯一ID
    "provider": str,          # Provider 名称 (openai/mock)
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

#### llm.call_result
LLM 返回结果（包含实际响应内容）。

**Payload 结构**:
```python
{
    "llm_call_id": str,
    "response": {
        "content": str,       # LLM 响应内容
        "tool_calls": list    # 工具调用列表 (如果有)
    },
    "usage": dict,            # Token 使用情况
    "finish_reason": str      # 结束原因 (stop/tool_calls/length/error)
}
```

**说明**:
- 此事件包含 LLM 的实际返回内容
- `response.content` 包含文本响应
- `response.tool_calls` 包含工具调用信息（如果 LLM 决定调用工具）
- 错误时 `finish_reason` 为 "error"，`content` 包含错误信息

#### llm.call_completed
LLM 调用完成（不包含结果内容）。

**Payload 结构**:
```python
{
    "llm_call_id": str
}
```

**说明**:
- 此事件仅表示 LLM 调用流程结束
- 不包含响应内容，内容在 `llm.call_result` 中
- 用于触发后续流程（如工具调用或结束对话）

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

#### tool.execution_start
工具内部执行开始（细粒度追踪）。

**Payload 结构**:
```python
{
    "tool_call_id": str,
    "tool_name": str
}
```

#### tool.execution_end
工具内部执行结束（细粒度追踪）。

**Payload 结构**:
```python
{
    "tool_call_id": str,
    "tool_name": str,
    "success": bool
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

### 5. Title 事件

#### agent.update_title_started
开始生成会话标题。

**Payload 结构**:
```python
{
    "user_input": str         # 用户第一条输入
}
```

#### agent.update_title_completed
会话标题生成完成。

**Payload 结构**:
```python
{
    "title": str,             # 生成的标题
    "success": bool,          # 是否成功
    "error": str              # 错误信息 (如果失败)
}
```

### 6. 错误事件

#### error.raised
系统发生错误。

**Payload 结构**:
```python
{
    "error_type": str,        # 错误类型
    "error_message": str,     # 错误消息
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
llm.call_result (包含响应内容)
    ↓
llm.call_completed
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
llm.call_result (包含 tool_calls)
    ↓
llm.call_completed
    ↓
tool.call_requested (可能多个并发)
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
llm.call_started
    ↓
llm.call_result (包含最终响应)
    ↓
llm.call_completed
    ↓
agent.step_completed
```

### 标题生成流程（异步）

```
ui.user_input (第一条消息)
    ↓
agent.update_title_started
    ↓
(异步 LLM 调用)
    ↓
agent.update_title_completed
```

## 事件总线实现

### PublicEventBus

系统使用单一的 PublicEventBus，所有模块都订阅这个总线。

**特点**:
- 使用 asyncio.Queue 实现
- 支持多订阅者模式（广播）
- 每个订阅者有独立的队列
- 事件持久化到数据库

**实现**:
```python
class PublicEventBus:
    def __init__(self):
        self._subscribers: set[asyncio.Queue[EventEnvelope]] = set()

    async def publish(self, event: EventEnvelope) -> None:
        # 广播给所有订阅者
        for q in list(self._subscribers):
            await q.put(event)

    async def subscribe(self) -> AsyncIterator[EventEnvelope]:
        queue = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)
```

### 事件过滤

各个 Runtime 模块订阅 PublicEventBus 后，自行过滤感兴趣的事件：

```python
async def _loop(self) -> None:
    async for event in self.publisher.bus.subscribe():
        if event.type == UI_USER_INPUT:
            await self._handle_user_input(event)
        elif event.type == LLM_CALL_RESULT:
            await self._handle_llm_result(event)
        # ...
```

### 会话隔离

虽然使用单一事件总线，但通过 `session_id` 实现会话隔离：
- 每个事件都携带 `session_id`
- Runtime 模块根据 `session_id` 处理对应会话的事件
- SessionStateStore 按 `session_id` 存储状态

## 事件持久化

所有事件都会存储到 SQLite 的 `events` 表中，用于：
- 会话回放
- 调试追踪
- 性能分析
- 审计日志

**存储字段**:
- event_id
- type
- session_id
- turn_id
- trace_id
- payload (JSON)
- source
- timestamp

## Gateway 事件路由

Gateway 负责在 Channel 和 PublicEventBus 之间路由事件：

### 上行路由（Channel → Bus）
1. Channel 接收用户输入
2. Channel 调用 `Gateway.publish_from_channel(event)`
3. Gateway 将事件发布到 PublicEventBus

### 下行路由（Bus → Channel）
1. Gateway 订阅 PublicEventBus
2. 根据 `session_id` 查找对应的 Channel
3. 调用 `Channel.send_event(event)` 发送给用户

## 设计优势

### 1. 解耦性
各模块通过事件通信，不直接依赖，易于测试和扩展。

### 2. 可观测性
所有事件都有完整的追踪信息（event_id、trace_id、timestamp），便于调试。

### 3. 可扩展性
新增模块只需订阅事件总线，无需修改现有代码。

### 4. 并发支持
多个工具可以并发执行，通过 `pending_tool_calls` 集合跟踪。

### 5. 持久化
事件自动持久化，支持会话回放和审计。

## 未来扩展

虽然当前使用内存队列，但架构设计已为分布式扩展预留空间：

- 使用 Redis Pub/Sub 替代内存队列
- 支持跨进程/跨机器的事件分发
- 事件流式处理和实时分析
- 事件重放和时间旅行调试
