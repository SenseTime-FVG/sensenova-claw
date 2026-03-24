# 会话状态管理

## 概述

Sensenova-Claw 采用**双层状态设计**：内存层（热数据，快速读写）+ SQLite 层（持久化，保证数据不丢失）。

```
┌─────────────────────────────────────┐
│       SessionStateStore（内存层）     │  ← 快速读写，活跃会话的工作状态
│  TurnState / 消息历史 / 轮次追踪      │
├─────────────────────────────────────┤
│       Repository / SQLite（持久化层） │  ← 完整历史，重启后可恢复
│  sessions / turns / messages / events│
└─────────────────────────────────────┘
```

---

## SessionStateStore（内存层）

`SessionStateStore` 维护所有活跃会话的内存状态，提供毫秒级读写。

### 核心数据结构

```python
class SessionStateStore:
    _turns: dict[tuple[str, str], TurnState]
    # key: (session_id, turn_id) → 当前轮次的完整状态

    _latest_turn: dict[str, str]
    # key: session_id → 该 session 的最新 turn_id

    _session_history: dict[str, list[dict]]
    # key: session_id → LLM 消息历史列表

    _session_first_turn: dict[str, bool]
    # key: session_id → 是否为首轮对话（懒加载标记）
```

### 字段说明

| 字段 | 类型 | 用途 |
|------|------|------|
| `_turns` | `dict[(session_id, turn_id), TurnState]` | 存储每个轮次的详细状态，包括用户输入、消息、工具调用状态、最终回复 |
| `_latest_turn` | `dict[session_id, turn_id]` | 快速查找某个 session 的当前活跃轮次 |
| `_session_history` | `dict[session_id, list[dict]]` | 累积的 LLM 消息历史，用于构建上下文 |
| `_session_first_turn` | `dict[session_id, bool]` | 标记是否为首轮对话。首轮时需要从 SQLite 加载历史消息 |

---

## TurnState 数据结构

`TurnState` 表示一次完整对话轮次（从 `user.input` 到 `agent.step_completed`）的状态。

```python
class TurnState:
    turn_id: str                    # 轮次 ID
    user_input: str                 # 用户输入文本
    messages: list[dict]            # 本轮累积的消息（含 LLM 回复和工具结果）
    pending_tool_calls: set[str]    # 等待结果的 tool_call_id 集合
    tool_results: list[dict]        # 已返回的工具执行结果
    final_response: str             # LLM 的最终文本响应
    history_offset: int             # 本轮新消息在历史中的起始索引
```

### 字段详细说明

#### turn_id

- 在收到 `user.input` 时生成（UUID v4）
- 同一轮次的所有事件共享此 ID

#### user_input

- 用户的原始输入文本
- 从 `user.input` 事件的 `payload.text` 提取

#### messages

- 本轮对话中累积的所有消息
- 包含：用户消息、LLM 的 assistant 消息（含 tool_calls）、工具结果消息
- 每次 LLM 调用循环都会追加新的消息

#### pending_tool_calls

- 当前等待结果的工具调用 ID 集合
- 当 LLM 返回 tool_calls 时，将所有 `tool_call_id` 加入此集合
- 每收到一个 `tool.call_result`，从集合中移除对应 ID
- **当集合为空时，表示所有并发工具执行完毕**，可以发起下一轮 LLM 调用

#### tool_results

- 已收到的工具执行结果列表
- 每个元素包含 `tool_call_id`、`result`、`success` 等信息
- 当所有工具完成后，统一组装成 tool 消息追加到 messages

#### final_response

- LLM 返回的最终文本回复（即无 tool_calls 的 stop 响应）
- 用于发布 `agent.step_completed` 事件和持久化

#### history_offset

- 本轮新消息在 `_session_history` 中的起始索引
- 用于在持久化时只写入本轮新增的消息，而非重写全部历史

---

## Message 格式

发送给 LLM 的消息遵循 OpenAI 兼容格式：

### 用户消息

```python
{
    "role": "user",
    "content": "帮我搜索最新的 AI 新闻"
}
```

### 系统消息

```python
{
    "role": "system",
    "content": "你是一个有用的AI助手...\n\n## 记忆\n...\n\n## 工作区\n..."
}
```

### 助手消息（纯文本回复）

```python
{
    "role": "assistant",
    "content": "根据搜索结果，最新的 AI 新闻包括..."
}
```

### 助手消息（工具调用）

```python
{
    "role": "assistant",
    "content": null,
    "tool_calls": [
        {
            "id": "call_abc123",
            "type": "function",
            "function": {
                "name": "serper_search",
                "arguments": "{\"query\": \"最新 AI 新闻\"}"
            }
        },
        {
            "id": "call_def456",
            "type": "function",
            "function": {
                "name": "fetch_url",
                "arguments": "{\"url\": \"https://example.com\"}"
            }
        }
    ]
}
```

> 注意：`tool_calls` 中每个条目必须包含 `type: "function"` 字段，否则 OpenAI 兼容网关会返回 `400 invalid_value` 错误。

### 工具结果消息

```python
{
    "role": "tool",
    "tool_call_id": "call_abc123",
    "name": "serper_search",
    "content": "搜索结果：1. ..."
}
```

---

## 状态变迁流程

一次完整对话轮次中，状态的变迁过程如下：

```
1. 收到 user.input
   │
   ├── 创建 TurnState(turn_id, user_input)
   ├── 更新 _latest_turn[session_id] = turn_id
   └── 如果 _session_first_turn[session_id] == True：
       └── 从 SQLite 加载历史消息到 _session_history[session_id]

2. 发起 LLM 调用
   │
   └── 从 _session_history 构建完整 messages 列表

3. 收到 llm.call_result（带 tool_calls）
   │
   ├── 追加 assistant 消息到 TurnState.messages
   └── 设置 pending_tool_calls = {call_id_1, call_id_2, ...}

4. 收到 tool.call_result（逐个到达）
   │
   ├── 追加到 TurnState.tool_results
   └── 从 pending_tool_calls 移除对应 call_id
       │
       └── pending_tool_calls 为空？
           ├── 否 → 继续等待
           └── 是 → 组装 tool 消息 → 追加到 messages → 回到步骤 2

5. 收到 llm.call_result（无 tool_calls，stop）
   │
   ├── 设置 TurnState.final_response = content
   ├── 追加 assistant 消息到 _session_history
   ├── 持久化到 SQLite（messages 表）
   └── 发布 agent.step_completed
```

---

## 首轮加载与懒加载

### 为什么需要懒加载

- 内存层不持久化，服务重启后 `_session_history` 为空
- 但 SQLite 中保存了完整历史
- 因此首轮对话时需要从 SQLite 加载历史消息

### 加载逻辑

```python
# 伪代码
if session_id not in _session_first_turn:
    _session_first_turn[session_id] = True

if _session_first_turn[session_id]:
    # 从 SQLite 加载历史消息
    history = await repository.get_session_messages(session_id)
    _session_history[session_id] = history
    _session_first_turn[session_id] = False
```

首轮标记确保只加载一次，后续轮次直接使用内存中的历史。

---

## SQLite 持久化层

SQLite 通过 `Repository` 提供持久化存储，包含以下核心表：

| 表名 | 存储内容 | 主要字段 |
|------|----------|----------|
| `sessions` | 会话元信息 | session_id, title, created_at, updated_at |
| `turns` | 对话轮次 | turn_id, session_id, user_input, created_at |
| `messages` | 消息记录 | message_id, session_id, turn_id, role, content, tool_calls |
| `events` | 全量事件日志 | event_id, type, session_id, payload, ts |

### 写入时机

- **session 创建**：首次收到 `user.input` 时写入 sessions 表
- **turn 记录**：每次 `agent.step_started` 时写入 turns 表
- **消息持久化**：`agent.step_completed` 时批量写入本轮的所有 messages
- **事件持久化**：EventPersister 独立订阅 PublicEventBus，实时写入 events 表
