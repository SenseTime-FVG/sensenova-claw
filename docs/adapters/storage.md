# 存储层

> 路径：`agentos/adapters/storage/`

存储层基于 SQLite 实现数据持久化，为上层提供 Repository 接口。

---

## 概览

- 使用 `sqlite3`（非 `aiosqlite`，因为在当前环境下更稳定）
- 数据库路径：`var/data/agentos.db`
- 通过 Repository 模式封装数据访问逻辑

---

## 数据表结构

### sessions 表

会话信息表，记录每个对话会话的元数据。

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | TEXT PK | 会话 ID |
| `created_at` | TEXT | 创建时间 |
| `last_active` | TEXT | 最后活跃时间 |
| `meta` | TEXT(JSON) | 元数据（title, agent_id 等） |
| `status` | TEXT | 状态 |
| `channel` | TEXT | 接入渠道 |
| `model` | TEXT | 使用的模型 |
| `message_count` | INTEGER | 消息数量 |

### turns 表

对话轮次表，记录每轮用户-Agent 交互的状态。

| 字段 | 类型 | 说明 |
|------|------|------|
| `turn_id` | TEXT PK | 轮次 ID |
| `session_id` | TEXT FK | 会话 ID |
| `status` | TEXT | 状态 |
| `started_at` | TEXT | 开始时间 |
| `ended_at` | TEXT | 结束时间 |
| `user_input` | TEXT | 用户输入 |
| `agent_response` | TEXT | Agent 响应 |

### messages 表

消息表，记录对话中的所有消息（用户、助手、工具、系统）。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增 ID |
| `session_id` | TEXT FK | 会话 ID |
| `turn_id` | TEXT FK | 轮次 ID |
| `role` | TEXT | 角色：user / assistant / tool / system |
| `content` | TEXT | 消息内容 |
| `tool_calls` | TEXT(JSON) | 工具调用（assistant 角色） |
| `tool_call_id` | TEXT | 工具调用 ID（tool 角色） |
| `tool_name` | TEXT | 工具名称 |
| `created_at` | TEXT | 创建时间 |

### events 表

事件表，记录系统中流转的所有事件，用于审计和调试。

| 字段 | 类型 | 说明 |
|------|------|------|
| `event_id` | TEXT PK | 事件 ID |
| `session_id` | TEXT | 会话 ID |
| `turn_id` | TEXT | 轮次 ID |
| `event_type` | TEXT | 事件类型 |
| `timestamp` | REAL | 时间戳 |
| `source` | TEXT | 来源 |
| `trace_id` | TEXT | 关联 ID |
| `payload_json` | TEXT | 事件数据 JSON |

### cron_jobs 表

定时任务定义表，存储 Cron 调度任务的配置。

| 字段 | 类型 | 说明 |
|------|------|------|
| `job_id` | TEXT PK | 任务 ID |
| `name` | TEXT | 任务名称 |
| `schedule` | TEXT | 调度表达式（如 cron 格式） |
| `payload` | TEXT(JSON) | 任务参数 |
| `enabled` | INTEGER | 是否启用（0/1） |
| `next_run_at_ms` | INTEGER | 下次执行时间（毫秒时间戳） |
| `created_at` | TEXT | 创建时间 |
| `updated_at` | TEXT | 更新时间 |

### cron_runs 表

定时任务执行记录表，记录每次任务执行的结果。

| 字段 | 类型 | 说明 |
|------|------|------|
| `run_id` | TEXT PK | 执行记录 ID |
| `job_id` | TEXT FK | 任务 ID |
| `started_at` | TEXT | 开始时间 |
| `finished_at` | TEXT | 结束时间 |
| `status` | TEXT | 执行状态（running / success / failed） |
| `result` | TEXT(JSON) | 执行结果 |

---

## Repository 接口

Repository 层封装了对各数据表的 CRUD 操作：

```python
# 会话相关
save_session(session) -> None
get_session(session_id) -> dict | None
list_sessions() -> list[dict]
delete_session(session_id) -> None

# 轮次相关
save_turn(turn) -> None
get_turns(session_id) -> list[dict]

# 消息相关
save_message(message) -> None
get_messages(session_id) -> list[dict]

# 事件相关
save_event(event) -> None
get_events(session_id) -> list[dict]
```

---

## 与内存状态的关系

- **SessionStateStore**：内存中维护当前活跃会话的状态（Turn、Message、工具调用状态），提供快速读写
- **SQLite Repository**：持久化存储，系统重启后可恢复历史数据
- 写入时同时更新内存状态和持久化存储，读取时优先从内存获取
