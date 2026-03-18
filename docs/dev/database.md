# 数据库 Schema

AgentOS 使用 SQLite 作为持久化存储，数据库文件位于 `var/data/agentos.db`。

## 核心表结构

### sessions 表

存储会话元信息。

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | TEXT PRIMARY KEY | 会话唯一标识（UUID） |
| `created_at` | REAL NOT NULL | 创建时间（Unix 时间戳） |
| `last_active` | REAL NOT NULL | 最后活跃时间（Unix 时间戳） |
| `meta` | TEXT | JSON 元数据（见下方结构） |
| `status` | TEXT | 会话状态，默认 `active` |
| `channel` | TEXT | 接入渠道标识（迁移添加） |
| `model` | TEXT | 使用的 LLM 模型（迁移添加） |
| `message_count` | INTEGER | 消息总数，默认 0（迁移添加） |

> `channel`、`model`、`message_count` 三列通过 ALTER TABLE 迁移添加，旧数据库首次启动时自动升级。

**meta JSON 结构**：

```json
{
  "title": "会话标题（自动生成）",
  "agent_id": "default",
  "model": "gpt-4o-mini"
}
```

### turns 表

存储对话轮次，一个 session 包含多个 turn。

| 字段 | 类型 | 说明 |
|------|------|------|
| `turn_id` | TEXT PRIMARY KEY | 轮次唯一标识（UUID） |
| `session_id` | TEXT | 外键 → sessions |
| `status` | TEXT | 状态（started / completed / cancelled） |
| `started_at` | TEXT | 开始时间 |
| `ended_at` | TEXT | 结束时间 |
| `user_input` | TEXT | 用户原始输入 |
| `agent_response` | TEXT | Agent 最终响应 |

### messages 表

存储 LLM 上下文中的消息，用于恢复对话历史。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PRIMARY KEY | 自增 ID |
| `session_id` | TEXT | 外键 → sessions |
| `turn_id` | TEXT | 外键 → turns |
| `role` | TEXT | 角色：user / assistant / tool / system |
| `content` | TEXT | 消息内容 |
| `tool_calls` | TEXT | JSON，工具调用信息（仅 assistant 角色） |
| `tool_call_id` | TEXT | 工具调用 ID（仅 tool 角色） |
| `tool_name` | TEXT | 工具名称（仅 tool 角色） |
| `created_at` | TEXT | 创建时间 |

**tool_calls JSON 结构**（assistant 角色）：

```json
[
  {
    "id": "call_abc123",
    "type": "function",
    "function": {
      "name": "bash_command",
      "arguments": "{\"command\": \"ls -la\"}"
    }
  }
]
```

### events 表

存储全量事件流，由 EventPersister 自动写入。

| 字段 | 类型 | 说明 |
|------|------|------|
| `event_id` | TEXT PRIMARY KEY | 事件唯一标识（UUID） |
| `session_id` | TEXT | 会话 ID |
| `turn_id` | TEXT | 轮次 ID |
| `event_type` | TEXT | 事件类型（如 `user.input`） |
| `timestamp` | REAL | Unix 时间戳 |
| `source` | TEXT | 来源：user / agent / llm / tool / system |
| `trace_id` | TEXT | 关联 ID（用于请求-响应匹配） |
| `payload_json` | TEXT | 事件数据 JSON |

> events 表是完整的审计日志，记录了系统内所有事件的流转。前端会话重放功能通过 `GET /api/sessions/{id}/events` 查询此表来重建消息历史。

### agent_messages 表

多 Agent 消息通信记录，用于 `send_message` 工具的状态追踪。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT PRIMARY KEY | 消息记录 ID |
| `parent_session_id` | TEXT NOT NULL | 父会话 ID |
| `parent_turn_id` | TEXT | 父轮次 ID |
| `parent_tool_call_id` | TEXT | 父工具调用 ID |
| `child_session_id` | TEXT NOT NULL | 子会话 ID |
| `target_id` | TEXT NOT NULL | 目标 Agent ID |
| `status` | TEXT NOT NULL | 消息状态 |
| `mode` | TEXT NOT NULL | 模式（sync / async） |
| `message` | TEXT NOT NULL | 消息内容 |
| `result` | TEXT | 执行结果 |
| `error` | TEXT | 错误信息 |
| `depth` | INTEGER NOT NULL | 消息深度，默认 0 |
| `pingpong_count` | INTEGER NOT NULL | 乒乓轮数，默认 0 |
| `active_turn_id` | TEXT | 当前活跃轮次 |
| `attempt_count` | INTEGER NOT NULL | 当前尝试次数，默认 1 |
| `max_attempts` | INTEGER NOT NULL | 最大尝试次数，默认 1 |
| `timeout_seconds` | REAL | 超时秒数 |
| `created_at` | REAL NOT NULL | 创建时间 |
| `completed_at` | REAL | 完成时间 |

### cron_jobs 表

定时任务定义。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT PRIMARY KEY | 任务 ID |
| `name` | TEXT | 任务名称 |
| `description` | TEXT | 任务描述 |
| `schedule_json` | TEXT NOT NULL | 调度配置 JSON |
| `session_target` | TEXT NOT NULL | 目标 session，默认 `isolated` |
| `wake_mode` | TEXT NOT NULL | 唤醒方式，默认 `now` |
| `payload_json` | TEXT NOT NULL | 任务数据 |
| `delivery_json` | TEXT | 投递配置 JSON |
| `enabled` | INTEGER NOT NULL | 是否启用，默认 1 |
| `delete_after_run` | INTEGER | 执行后是否删除 |
| `created_at_ms` | INTEGER NOT NULL | 创建时间（毫秒） |
| `updated_at_ms` | INTEGER NOT NULL | 更新时间（毫秒） |
| `next_run_at_ms` | INTEGER | 下次执行时间（毫秒） |
| `running_at_ms` | INTEGER | 当前执行开始时间 |
| `last_run_at_ms` | INTEGER | 上次执行时间 |
| `last_run_status` | TEXT | 上次执行状态 |
| `last_error` | TEXT | 上次执行错误 |
| `last_duration_ms` | INTEGER | 上次执行耗时 |
| `consecutive_errors` | INTEGER NOT NULL | 连续错误次数，默认 0 |

### cron_runs 表

定时任务执行记录。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PRIMARY KEY | 自增执行记录 ID |
| `job_id` | TEXT | 外键 → cron_jobs |
| `started_at_ms` | INTEGER | 执行开始时间 |
| `status` | TEXT | 状态 |
| `error` | TEXT | 错误信息 |
| `duration_ms` | INTEGER | 执行耗时 |
| `session_id` | TEXT | 关联的临时 session |

## 表关系

```
sessions (1) ──→ (N) turns
sessions (1) ──→ (N) messages
sessions (1) ──→ (N) events
sessions (1) ──→ (N) agent_messages (parent_session_id)
sessions (1) ──→ (N) agent_messages (child_session_id)
turns    (1) ──→ (N) messages
cron_jobs(1) ──→ (N) cron_runs
```

## 数据流向

| 写入时机 | 写入的表 | 触发者 |
|----------|---------|--------|
| 用户首次发消息 | sessions | AgentSessionWorker |
| 每轮对话开始/结束 | turns | AgentSessionWorker |
| LLM 上下文中的每条消息 | messages | AgentSessionWorker |
| 所有事件流转 | events | EventPersister |
| 多 Agent 消息通信 | agent_messages | AgentMessageCoordinator |
| 创建/执行定时任务 | cron_jobs / cron_runs | CronRuntime |

## 注意事项

- 使用 `sqlite3` 而非 `aiosqlite`（更稳定）
- 首轮对话时从 messages 表加载历史到内存 `SessionStateStore._session_history`
- events 表数据量增长较快，可用于调试和审计
