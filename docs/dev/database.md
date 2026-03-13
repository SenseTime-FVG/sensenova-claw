# 数据库 Schema

AgentOS 使用 SQLite 作为持久化存储，数据库文件位于 `var/data/agentos.db`。

## 核心表结构

### sessions 表

存储会话元信息。

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | TEXT PRIMARY KEY | 会话唯一标识（UUID） |
| `created_at` | TEXT | 创建时间（ISO 8601） |
| `last_active` | TEXT | 最后活跃时间 |
| `meta` | TEXT | JSON 元数据（见下方结构） |
| `status` | TEXT | 会话状态 |
| `channel` | TEXT | 接入渠道标识 |
| `model` | TEXT | 使用的 LLM 模型 |
| `message_count` | INTEGER | 消息总数 |

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

### cron_jobs 表

定时任务定义。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT PRIMARY KEY | 任务 ID |
| `name` | TEXT | 任务名称 |
| `schedule_json` | TEXT | 调度配置 JSON |
| `session_target` | TEXT | 目标 session |
| `wake_mode` | TEXT | 唤醒方式 |
| `payload_json` | TEXT | 任务数据 |
| `enabled` | INTEGER | 是否启用 |
| `next_run_at_ms` | INTEGER | 下次执行时间（毫秒） |
| `running_at_ms` | INTEGER | 当前执行开始时间 |

### cron_runs 表

定时任务执行记录。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT PRIMARY KEY | 执行记录 ID |
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
| 创建/执行定时任务 | cron_jobs / cron_runs | CronRuntime |

## 注意事项

- 使用 `sqlite3` 而非 `aiosqlite`（更稳定）
- 首轮对话时从 messages 表加载历史到内存 `SessionStateStore._session_history`
- events 表数据量增长较快，可用于调试和审计
