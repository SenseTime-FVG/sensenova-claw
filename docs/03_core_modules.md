# 核心模块设计

本文档描述 AgentOS 的核心运行时模块。

## AgentRuntime 模块

AgentRuntime 是系统的核心执行引擎，负责协调整个对话流程。

### 设计原则

**事件驱动而非循环驱动**

传统的 Agent 实现通常使用循环：
```python
# 传统方式 (不采用)
while not done:
    response = llm.call(messages)
    if response.tool_calls:
        results = execute_tools(response.tool_calls)
        messages.append(results)
    else:
        done = True
```

AgentOS 采用事件驱动方式，通过监听和发布事件来推进流程，实现更好的解耦和可观测性。

### 核心职责

1. **会话管理**: 创建和维护 session_id、turn_id
2. **流程编排**: 根据事件决定下一步动作
3. **上下文构建**: 调用 ContextBuilder 准备 LLM 输入
4. **事件发布**: 发布各阶段的状态事件

### 状态管理

AgentRuntime 通过 SessionStateStore 管理会话状态，每个 turn 包含：
- `turn_id`: 对话轮次ID
- `user_input`: 用户输入
- `messages`: 消息历史
- `pending_tool_calls`: 待完成的工具调用集合
- `tool_results`: 工具执行结果列表
- `final_response`: 最终响应

### 事件流转

```
IDLE → PROCESSING_INPUT → WAITING_LLM → WAITING_TOOL → COMPLETED
  ↑                                          ↓
  └──────────────────────────────────────────┘
```

### 事件处理逻辑

#### 接收 ui.user_input 事件
```python
1. 创建或更新 session（如果是新会话）
2. 生成 turn_id
3. 从 SessionStateStore 获取历史消息
4. 调用 ContextBuilder.build_messages() 构建消息列表
5. 初始化 TurnState 并存储
6. 发布 agent.step_started
7. 发布 llm.call_requested
```

#### 接收 llm.call_result 事件
```python
1. 从 payload 中提取 response（包含 content 和 tool_calls）
2. 构建 assistant 消息
3. 如果有 tool_calls，添加到消息中
4. 将 assistant 消息添加到 TurnState.messages
```

#### 接收 llm.call_completed 事件
```python
1. 从最后一条 assistant 消息中获取 tool_calls
2. 如果有 tool_calls:
   - 记录到 pending_tool_calls 集合
   - 为每个工具调用发布 tool.call_requested
3. 如果没有 tool_calls:
   - 保存最终响应到数据库
   - 将本轮消息添加到会话历史
   - 发布 agent.step_completed
```

#### 接收 tool.call_completed 事件
```python
1. 从 pending_tool_calls 中移除已完成的工具
2. 将工具结果添加到 tool_results
3. 调用 ContextBuilder.append_tool_result() 添加到消息历史
4. 如果所有工具都已完成:
   - 发布新的 llm.call_requested（带工具结果）
```

### 并发工具调用

当 LLM 返回多个工具调用时，AgentRuntime 会并发执行所有工具，提升效率。

```python
# 实际实现
tool_calls = last_assistant_message.get("tool_calls", [])
state.pending_tool_calls = {call["id"] for call in tool_calls}

for call in tool_calls:
    await publisher.publish(EventEnvelope(
        type=TOOL_CALL_REQUESTED,
        payload={
            "tool_call_id": call["id"],
            "tool_name": call["name"],
            "arguments": call.get("arguments", {})
        }
    ))
```

## TitleRuntime 模块

TitleRuntime 负责为新会话自动生成标题。

### 核心功能

1. 监听 `ui.user_input` 事件
2. 对于每个会话的第一条消息，异步生成标题
3. 使用 LLM 根据用户输入生成简短标题（不超过10字）
4. 更新数据库中的会话标题

### 实现要点

- 使用独立的 LLM 调用，不影响主对话流程
- 异步执行，不阻塞用户交互
- 失败时记录日志但不影响系统运行
- 每个会话只生成一次标题（通过 `_processed_sessions` 集合跟踪）

### 标题生成 Prompt

```python
system_prompt = "你是一个会话标题生成助手。根据用户的第一个问题，生成一个简短的会话标题（不超过10个字）。只返回标题文本，不要有其他内容。"
user_prompt = f"用户问题：{user_input}\n\n请生成会话标题："
```

## LLMRuntime 模块

LLMRuntime 负责处理 LLM 调用请求。

### 核心功能

1. 监听 `llm.call_requested` 事件
2. 根据配置选择 LLM Provider
3. 调用 LLM API
4. 发布 `llm.call_result` 和 `llm.call_completed` 事件

### 支持的提供商

- **OpenAI**: gpt-5.2 等
- **OpenAI 兼容**: 任何兼容 OpenAI API 的服务（通过配置 base_url）
- **Mock**: 测试用的模拟 Provider

### 事件处理流程

```python
1. 接收 llm.call_requested 事件
2. 记录 DEBUG 日志（包含完整的 messages 和 tools）
3. 发布 llm.call_started
4. 调用 Provider.call()
5. 发布 llm.call_result（包含响应内容）
6. 发布 llm.call_completed
```

### 错误处理

- API 调用失败时发布 `error.raised` 事件
- 错误时也发布 `llm.call_result` 事件（content 包含错误信息）
- 最后发布 `llm.call_completed` 确保流程继续

### 消息归一化

OpenAI Provider 会对消息进行归一化处理：

1. 为 `tool_calls` 添加 `type: "function"` 字段
2. 确保 `tool` 消息包含 `tool_call_id` 字段
3. 将 `arguments` 从 dict 转换为 JSON 字符串

这样可以避免因格式问题导致的 API 调用失败（如 400 invalid_value 错误）。

## ToolRuntime 模块

详细的工具文档请参考 [12_builtin_tools.md](./12_builtin_tools.md)。

ToolRuntime 负责工具的注册、管理和执行。

### 核心功能

1. 监听 `tool.call_requested` 事件
2. 查找并执行对应的工具
3. 处理超时和错误
4. 发布工具执行结果

### 事件处理流程

```python
1. 接收 tool.call_requested 事件
2. 发布 tool.call_started
3. 查找对应的 Tool 实例
4. 发布 tool.execution_start
5. 执行 Tool.execute() (带超时控制)
6. 发布 tool.execution_end
7. 发布 tool.call_completed (包含结果或错误)
```

### 结果截断机制

当工具返回结果过长时（超过约16000 tokens），ToolRuntime 会：

1. 保存完整结果到文件：`<workspace>/<session_id>/tool_result_<id>.txt`
2. 截断结果并附加文件路径提示
3. 将截断后的结果返回给 LLM

这样既避免了 token 超限，又保留了完整数据供后续使用。

### 超时控制

所有工具执行都使用 `asyncio.wait_for()` 进行超时控制，默认15秒。可通过配置修改：

```yaml
tools:
  bash_command:
    timeout: 30
  serper_search:
    timeout: 20
```

## ContextBuilder 模块

ContextBuilder 负责构建发送给 LLM 的消息列表。

### 核心功能

1. **初始化系统提示**: 加载 Agent 的系统提示词
2. **注入系统信息**: 添加系统类型和当前时间
3. **添加历史消息**: 从 SessionStateStore 获取历史对话
4. **添加用户输入**: 为用户消息添加时间戳
5. **添加工具结果**: 将工具执行结果格式化为消息

### 系统信息注入

ContextBuilder 会自动在系统提示中注入：
- 系统类型（Linux/Windows/macOS）
- 当前时间（YYYY-MM-DD HH:MM:SS）

用户消息也会自动添加时间戳前缀：`[2024-03-07 10:30:00] 用户输入内容`

### 消息格式

遵循 OpenAI 的消息格式标准：

```python
[
    {"role": "system", "content": "..."},
    {"role": "user", "content": "[时间戳] ..."},
    {"role": "assistant", "content": "...", "tool_calls": [...]},
    {"role": "tool", "tool_call_id": "...", "name": "...", "content": "..."}
]
```

### 工具结果处理

```python
def append_tool_result(messages, tool_name, result, tool_call_id):
    content = result if isinstance(result, str) else json.dumps(result)
    tool_message = {
        "role": "tool",
        "name": tool_name,
        "content": content
    }
    if tool_call_id:
        tool_message["tool_call_id"] = tool_call_id
    messages.append(tool_message)
    return messages
```

## SessionStateStore 模块

SessionStateStore 管理会话和对话轮次的内存状态。

### 核心功能

1. **Turn 状态管理**: 存储每个 turn 的状态（消息、工具调用等）
2. **会话历史**: 维护每个会话的消息历史
3. **首轮标记**: 跟踪每个会话是否已处理第一轮对话

### 数据结构

```python
@dataclass
class TurnState:
    turn_id: str
    user_input: str
    messages: list[dict]                # 本轮的消息列表
    pending_tool_calls: set[str]        # 待完成的工具调用ID
    tool_results: list[dict]            # 工具执行结果
    final_response: str                 # 最终响应
```

### 存储说明

- 状态存储在内存中，重启后会丢失
- 持久化数据（会话、消息）存储在 SQLite 数据库中
- SessionStateStore 主要用于运行时状态管理，不负责持久化

### 主要方法

- `set_turn()`: 存储 turn 状态
- `get_turn()`: 获取 turn 状态
- `get_session_history()`: 获取会话历史消息
- `append_to_history()`: 添加消息到会话历史
- `is_first_turn()`: 检查是否是会话的第一轮对话

## 模块协作流程

完整的对话流程涉及多个模块的协作：

```
用户输入
  ↓
Gateway → PublicEventBus (ui.user_input)
  ↓
AgentRuntime:
  - 创建 session 和 turn
  - 构建消息（ContextBuilder）
  - 发布 llm.call_requested
  ↓
LLMRuntime:
  - 调用 LLM API
  - 发布 llm.call_result
  - 发布 llm.call_completed
  ↓
AgentRuntime:
  - 处理 LLM 响应
  - 如有工具调用，发布 tool.call_requested
  ↓
ToolRuntime:
  - 执行工具
  - 发布 tool.call_completed
  ↓
AgentRuntime:
  - 收集工具结果
  - 发布新的 llm.call_requested
  ↓
（循环直到没有工具调用）
  ↓
AgentRuntime:
  - 保存最终响应
  - 发布 agent.step_completed
  ↓
Gateway → 返回给用户
```

同时，TitleRuntime 在后台异步为新会话生成标题，不影响主流程。
