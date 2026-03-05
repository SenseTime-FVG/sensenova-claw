# 数据库设计

## 概述

AgentOS 使用 SQLite 作为本地数据存储方案，主要存储会话信息、对话轮次和事件日志。

## 数据库位置

- 主数据库文件: `~/.SenseAssistant/agentos.db`

## 表结构设计

### sessions 表

存储会话的基本信息。

```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,           -- Unix timestamp
    last_active REAL NOT NULL,          -- Unix timestamp
    meta TEXT,                          -- JSON 格式的元数据
    status TEXT DEFAULT 'active'        -- active/archived/deleted
);

CREATE INDEX idx_sessions_created ON sessions(created_at);
CREATE INDEX idx_sessions_last_active ON sessions(last_active);
```

**meta 字段示例**:
```json
{
    "title": "重构登录模块",
    "tags": ["refactor", "auth"],
    "model": "gpt-4",
    "total_turns": 5,
    "total_tokens": 12450
}
```

### turns 表

存储每个对话轮次的信息。

```sql
CREATE TABLE turns (
    turn_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    status TEXT NOT NULL,               -- started/completed/failed/cancelled
    started_at REAL NOT NULL,           -- Unix timestamp
    ended_at REAL,                      -- Unix timestamp
    user_input TEXT,                    -- 用户输入内容
    agent_response TEXT,                -- Agent 最终响应
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX idx_turns_session ON turns(session_id);
CREATE INDEX idx_turns_started ON turns(started_at);
```

### events 表

存储所有事件的完整记录，用于追踪和回放。

```sql
CREATE TABLE events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    turn_id TEXT,
    event_type TEXT NOT NULL,           -- 事件类型
    timestamp REAL NOT NULL,            -- Unix timestamp
    source TEXT NOT NULL,               -- ui/agent/llm/tool/system
    trace_id TEXT,                      -- 追踪ID
    payload_json TEXT NOT NULL,         -- JSON 格式的完整 payload
    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    FOREIGN KEY (turn_id) REFERENCES turns(turn_id)
);

CREATE INDEX idx_events_session ON events(session_id);
CREATE INDEX idx_events_turn ON events(turn_id);
CREATE INDEX idx_events_type ON events(event_type);
CREATE INDEX idx_events_timestamp ON events(timestamp);
CREATE INDEX idx_events_trace ON events(trace_id);
```

## 数据访问层

### 会话操作

```python
# 创建新会话
def create_session(session_id: str, meta: dict = None) -> None:
    now = time.time()
    conn.execute(
        "INSERT INTO sessions (session_id, created_at, last_active, meta) VALUES (?, ?, ?, ?)",
        (session_id, now, now, json.dumps(meta or {}))
    )

# 更新会话活跃时间
def update_session_activity(session_id: str) -> None:
    conn.execute(
        "UPDATE sessions SET last_active = ? WHERE session_id = ?",
        (time.time(), session_id)
    )

# 获取会话列表
def list_sessions(limit: int = 50) -> list:
    cursor = conn.execute(
        "SELECT * FROM sessions ORDER BY last_active DESC LIMIT ?",
        (limit,)
    )
    return cursor.fetchall()
```

### 轮次操作

```python
# 创建新轮次
def create_turn(turn_id: str, session_id: str, user_input: str) -> None:
    conn.execute(
        "INSERT INTO turns (turn_id, session_id, status, started_at, user_input) VALUES (?, ?, ?, ?, ?)",
        (turn_id, session_id, "started", time.time(), user_input)
    )

# 完成轮次
def complete_turn(turn_id: str, agent_response: str) -> None:
    conn.execute(
        "UPDATE turns SET status = ?, ended_at = ?, agent_response = ? WHERE turn_id = ?",
        ("completed", time.time(), agent_response, turn_id)
    )
```

### 事件操作

```python
# 记录事件
def log_event(event: EventEnvelope) -> None:
    conn.execute(
        """INSERT INTO events
           (event_id, session_id, turn_id, event_type, timestamp, source, trace_id, payload_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event.event_id,
            event.session_id,
            event.turn_id,
            event.type,
            event.ts,
            event.source,
            event.trace_id,
            json.dumps(event.payload)
        )
    )

# 查询会话的所有事件
def get_session_events(session_id: str) -> list:
    cursor = conn.execute(
        "SELECT * FROM events WHERE session_id = ? ORDER BY timestamp",
        (session_id,)
    )
    return cursor.fetchall()

# 根据 trace_id 查询相关事件
def get_events_by_trace(trace_id: str) -> list:
    cursor = conn.execute(
        "SELECT * FROM events WHERE trace_id = ? ORDER BY timestamp",
        (trace_id,)
    )
    return cursor.fetchall()
```

## 数据清理策略

### 归档旧会话

```python
def archive_old_sessions(days: int = 30) -> None:
    cutoff = time.time() - (days * 86400)
    conn.execute(
        "UPDATE sessions SET status = 'archived' WHERE last_active < ? AND status = 'active'",
        (cutoff,)
    )
```

### 删除事件日志

```python
def cleanup_old_events(days: int = 90) -> None:
    cutoff = time.time() - (days * 86400)
    conn.execute(
        "DELETE FROM events WHERE timestamp < ?",
        (cutoff,)
    )
```

## 性能优化

### 批量插入事件

高频事件写入时使用批量插入提升性能：

```python
def batch_log_events(events: list[EventEnvelope]) -> None:
    data = [
        (e.event_id, e.session_id, e.turn_id, e.type, e.ts, e.source, e.trace_id, json.dumps(e.payload))
        for e in events
    ]
    conn.executemany(
        """INSERT INTO events
           (event_id, session_id, turn_id, event_type, timestamp, source, trace_id, payload_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        data
    )
```

### 连接池

使用连接池管理数据库连接，避免频繁打开关闭：

```python
import sqlite3
from contextlib import contextmanager

class DatabasePool:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    @contextmanager
    def get_connection(self):
        yield self.conn
```
