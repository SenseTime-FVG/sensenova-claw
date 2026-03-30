from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from sensenova_claw.kernel.runtime.message_record import MessageRecord
from sensenova_claw.platform.config.config import config
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import PROACTIVE_RESULT, USER_INPUT

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    last_active REAL NOT NULL,
    meta TEXT,
    status TEXT DEFAULT 'active'
);
CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at);
CREATE INDEX IF NOT EXISTS idx_sessions_last_active ON sessions(last_active);

CREATE TABLE IF NOT EXISTS turns (
    turn_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at REAL NOT NULL,
    ended_at REAL,
    user_input TEXT,
    agent_response TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);
CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id);
CREATE INDEX IF NOT EXISTS idx_turns_started ON turns(started_at);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    turn_id TEXT,
    event_type TEXT NOT NULL,
    timestamp REAL NOT NULL,
    source TEXT NOT NULL,
    trace_id TEXT,
    payload_json TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    FOREIGN KEY (turn_id) REFERENCES turns(turn_id)
);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_turn ON events(turn_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_trace ON events(trace_id);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT,
    tool_calls TEXT,
    tool_call_id TEXT,
    tool_name TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    FOREIGN KEY (turn_id) REFERENCES turns(turn_id)
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_turn ON messages(turn_id);

CREATE TABLE IF NOT EXISTS agent_messages (
    id TEXT PRIMARY KEY,
    parent_session_id TEXT NOT NULL,
    parent_turn_id TEXT,
    parent_tool_call_id TEXT,
    child_session_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    status TEXT NOT NULL,
    mode TEXT NOT NULL,
    message TEXT NOT NULL,
    result TEXT,
    error TEXT,
    depth INTEGER NOT NULL DEFAULT 0,
    pingpong_count INTEGER NOT NULL DEFAULT 0,
    active_turn_id TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 1,
    max_attempts INTEGER NOT NULL DEFAULT 1,
    timeout_seconds REAL,
    created_at REAL NOT NULL,
    completed_at REAL
);
CREATE INDEX IF NOT EXISTS idx_agent_messages_parent_session ON agent_messages(parent_session_id);
CREATE INDEX IF NOT EXISTS idx_agent_messages_child_session ON agent_messages(child_session_id);
CREATE INDEX IF NOT EXISTS idx_agent_messages_status ON agent_messages(status);

CREATE TABLE IF NOT EXISTS cron_jobs (
    id TEXT PRIMARY KEY,
    name TEXT,
    description TEXT,
    schedule_json TEXT NOT NULL,
    session_target TEXT NOT NULL DEFAULT 'isolated',
    wake_mode TEXT NOT NULL DEFAULT 'now',
    payload_json TEXT NOT NULL,
    delivery_json TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    delete_after_run INTEGER,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    next_run_at_ms INTEGER,
    running_at_ms INTEGER,
    last_run_at_ms INTEGER,
    last_run_status TEXT,
    last_error TEXT,
    last_duration_ms INTEGER,
    consecutive_errors INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cron_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    started_at_ms INTEGER NOT NULL,
    ended_at_ms INTEGER,
    status TEXT,
    error TEXT,
    duration_ms INTEGER,
    session_id TEXT,
    delivery_status TEXT,
    job_name TEXT,
    job_text TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (job_id) REFERENCES cron_jobs(id)
);
CREATE INDEX IF NOT EXISTS idx_cron_runs_job ON cron_runs(job_id);

CREATE TABLE IF NOT EXISTS proactive_jobs (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    name TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    trigger_json TEXT NOT NULL,
    task_json TEXT NOT NULL,
    delivery_json TEXT NOT NULL,
    safety_json TEXT NOT NULL,
    state_json TEXT NOT NULL DEFAULT '{}',
    source TEXT DEFAULT 'config',
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS proactive_runs (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    session_id TEXT,
    status TEXT NOT NULL,
    triggered_by TEXT NOT NULL,
    started_at_ms INTEGER NOT NULL,
    completed_at_ms INTEGER,
    result_summary TEXT,
    error_message TEXT,
    FOREIGN KEY (job_id) REFERENCES proactive_jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_proactive_runs_job_id ON proactive_runs(job_id);
"""


class Repository:
    def __init__(self, db_path: str | None = None):
        if not db_path:
            db_path = config.get("system.database_path", "")
        if not db_path:
            from sensenova_claw.platform.config.workspace import resolve_sensenova_claw_home
            db_path = str(resolve_sensenova_claw_home(config) / "data" / "sensenova-claw.db")
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()  # 线程本地连接存储

    def _conn(self) -> sqlite3.Connection:
        """返回当前线程的 SQLite 连接（线程本地复用，首次创建时启用 WAL 模式）

        注意：threading.local 已保证每个线程独占一个连接，连接永远不会跨线程共享，
        因此不需要也不应该设置 check_same_thread=False（保持默认 True 以保留安全检查）。

        TODO: Task 2-6 完成后，所有 async 方法将迁移至 asyncio.to_thread + _sync_* 模式，
        届时业务方法中的 conn.close() + self._local.conn = None 均可删除（连接将持久复用）。
        """
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path)  # 默认 check_same_thread=True，保留驱动安全检查
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")   # 读写并发，减少锁竞争
            conn.execute("PRAGMA synchronous=NORMAL")  # 降低 fsync 频率，性能与安全的平衡
            self._local.conn = conn
        return conn

    async def init(self) -> None:
        await asyncio.to_thread(self._sync_init)

    def _sync_init(self) -> None:
        conn = self._conn()
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        self._migrate_sessions_table(conn)
        self._migrate_agent_messages_table(conn)
        self._migrate_cron_runs_table(conn)

    async def create_session(self, session_id: str, meta: dict[str, Any] | None = None) -> None:
        now = time.time()
        meta = meta or {}
        agent_id = meta.get("agent_id", "default")
        conn = self._conn()
        conn.execute(
            "INSERT OR IGNORE INTO sessions (session_id, created_at, last_active, meta, agent_id) VALUES (?, ?, ?, ?, ?)",
            (session_id, now, now, json.dumps(meta, ensure_ascii=False), agent_id),
        )
        conn.commit()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接

    async def update_session_activity(self, session_id: str) -> None:
        await asyncio.to_thread(self._sync_update_session_activity, session_id)

    def _sync_update_session_activity(self, session_id: str) -> None:
        conn = self._conn()
        conn.execute("UPDATE sessions SET last_active = ? WHERE session_id = ?", (time.time(), session_id))
        conn.commit()

    async def update_session_title(self, session_id: str, title: str) -> None:
        conn = self._conn()
        # 获取当前 meta
        row = conn.execute("SELECT meta FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if row:
            meta = json.loads(row[0]) if row[0] else {}
            meta["title"] = title
            conn.execute("UPDATE sessions SET meta = ? WHERE session_id = ?", (json.dumps(meta, ensure_ascii=False), session_id))
            conn.commit()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接

    async def list_sessions(
        self,
        limit: int = 50,
        *,
        include_hidden: bool = False,
    ) -> list[dict[str, Any]]:
        conn = self._conn()
        rows = conn.execute(
            """
            SELECT s.*,
                   lt.status AS last_turn_status,
                   lt.ended_at AS last_turn_ended_at,
                   lt.agent_response AS last_agent_response
            FROM sessions s
            LEFT JOIN (
                SELECT session_id,
                       status,
                       ended_at,
                       agent_response,
                       ROW_NUMBER() OVER (PARTITION BY session_id ORDER BY started_at DESC) AS rn
                FROM turns
            ) lt ON lt.session_id = s.session_id AND lt.rn = 1
            ORDER BY s.last_active DESC
            """,
        ).fetchall()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接
        sessions = [dict(row) for row in rows]
        if not include_hidden:
            sessions = [row for row in sessions if not self._is_hidden_session(row.get("meta"))]
        return sessions[:limit]

    async def create_turn(self, turn_id: str, session_id: str, user_input: str) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO turns (turn_id, session_id, status, started_at, user_input) VALUES (?, ?, ?, ?, ?)",
            (turn_id, session_id, "started", time.time(), user_input),
        )
        conn.commit()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接

    async def complete_turn(self, turn_id: str, agent_response: str) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE turns SET status = ?, ended_at = ?, agent_response = ? WHERE turn_id = ?",
            ("completed", time.time(), agent_response, turn_id),
        )
        conn.commit()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接

    async def update_turn_status(
        self,
        turn_id: str,
        status: str,
        agent_response: str | None = None,
    ) -> None:
        """更新 turn 状态，必要时补充结束时间与最终输出。"""
        conn = self._conn()
        conn.execute(
            "UPDATE turns SET status = ?, ended_at = ?, agent_response = ? WHERE turn_id = ?",
            (status, time.time(), agent_response, turn_id),
        )
        conn.commit()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接

    async def log_event(self, event: EventEnvelope) -> None:
        await asyncio.to_thread(self._sync_log_event, event)

    def _sync_log_event(self, event: EventEnvelope) -> None:
        conn = self._conn()
        conn.execute(
            """INSERT INTO events (event_id, session_id, turn_id, event_type, timestamp, source, trace_id, payload_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.event_id,
                event.session_id,
                event.turn_id,
                event.type,
                event.ts,
                event.source,
                event.trace_id,
                json.dumps(event.payload, ensure_ascii=False),
            ),
        )
        conn.commit()

    async def get_session_events(self, session_id: str) -> list[dict[str, Any]]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM events WHERE session_id = ? ORDER BY timestamp", (session_id,)).fetchall()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接
        return [dict(row) for row in rows]

    def _parse_payload_json(self, raw: str | bytes | None) -> dict[str, Any]:
        """解析 events.payload_json，失败时回退为空 dict。"""
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _list_consumed_recommendation_ids(
        self,
        conn: sqlite3.Connection,
        *,
        source_session_id: str,
        after_timestamp: float,
    ) -> set[str]:
        """读取某个 source session 在推荐生成后已消费的 recommendation_id 集合。"""
        rows = conn.execute(
            """
            SELECT payload_json
            FROM events
            WHERE event_type = ? AND session_id = ? AND timestamp > ?
            ORDER BY timestamp
            """,
            (USER_INPUT, source_session_id, after_timestamp),
        ).fetchall()

        consumed_ids: set[str] = set()
        for row in rows:
            payload = self._parse_payload_json(row["payload_json"])
            meta = payload.get("meta")
            if not isinstance(meta, dict):
                continue
            recommendation_id = str(meta.get("recommendation_id") or "").strip()
            if recommendation_id:
                consumed_ids.add(recommendation_id)
        return consumed_ids

    async def list_pending_recommendations(self, limit: int = 3) -> list[dict[str, Any]]:
        """聚合最近未消费的 turn_end 下一问推荐。"""
        if limit <= 0:
            return []

        conn = self._conn()
        rows = conn.execute(
            """
            SELECT event_id, session_id, timestamp, payload_json
            FROM events
            WHERE event_type = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (PROACTIVE_RESULT, max(limit * 20, 100)),
        ).fetchall()

        pending: list[dict[str, Any]] = []
        seen_source_sessions: set[str] = set()

        for row in rows:
            payload = self._parse_payload_json(row["payload_json"])
            if str(payload.get("recommendation_type") or "") != "turn_end":
                continue

            source_session_id = str(
                payload.get("source_session_id")
                or payload.get("session_id")
                or row["session_id"]
                or ""
            ).strip()
            if not source_session_id or source_session_id in seen_source_sessions:
                continue

            items = payload.get("items")
            if not isinstance(items, list) or not items:
                continue

            consumed_ids = self._list_consumed_recommendation_ids(
                conn,
                source_session_id=source_session_id,
                after_timestamp=float(row["timestamp"]),
            )

            remaining_items: list[dict[str, Any]] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_id = str(item.get("id") or "").strip()
                if item_id and item_id in consumed_ids:
                    continue
                remaining_items.append({
                    "id": item_id,
                    "title": str(item.get("title") or ""),
                    "prompt": str(item.get("prompt") or ""),
                    "category": str(item.get("category") or "") or None,
                })

            if not remaining_items:
                seen_source_sessions.add(source_session_id)
                continue

            pending.append({
                "job_id": str(payload.get("job_id") or ""),
                "job_name": str(payload.get("job_name") or ""),
                "session_id": str(payload.get("session_id") or row["session_id"] or ""),
                "source_session_id": source_session_id,
                "recommendation_type": "turn_end",
                "received_at_ms": int(float(row["timestamp"]) * 1000),
                "items": remaining_items[:5],
            })
            seen_source_sessions.add(source_session_id)

            if len(pending) >= limit:
                break

        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接
        return pending

    async def get_session_turns(self, session_id: str) -> list[dict[str, Any]]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM turns WHERE session_id = ? ORDER BY started_at",
            (session_id,),
        ).fetchall()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接
        return [dict(row) for row in rows]

    # ---------- Sessions 表迁移 ----------

    def _migrate_sessions_table(self, conn: sqlite3.Connection) -> None:
        """为 sessions 表添加新列（如不存在），并回填 agent_id"""
        cursor = conn.execute("PRAGMA table_info(sessions)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        migrations = [
            ("channel", "ALTER TABLE sessions ADD COLUMN channel TEXT"),
            ("model", "ALTER TABLE sessions ADD COLUMN model TEXT"),
            ("message_count", "ALTER TABLE sessions ADD COLUMN message_count INTEGER DEFAULT 0"),
            ("agent_id", "ALTER TABLE sessions ADD COLUMN agent_id TEXT DEFAULT 'default'"),
        ]
        for col, sql in migrations:
            if col not in existing_cols:
                conn.execute(sql)
        conn.commit()

    @staticmethod
    def _is_hidden_session(meta_raw: Any) -> bool:
        """根据 session meta 判定是否为 hidden session。"""
        if not meta_raw:
            return False
        try:
            meta = json.loads(meta_raw) if isinstance(meta_raw, str) else dict(meta_raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            return False
        return str(meta.get("visibility", "")).strip().lower() == "hidden"
        # 回填：从 meta JSON 中提取 agent_id 写入 agent_id 列（修复历史数据）
        rows = conn.execute(
            "SELECT session_id, meta FROM sessions WHERE agent_id IS NULL OR agent_id = 'default'"
        ).fetchall()
        for row in rows:
            meta_str = row[1]
            if not meta_str:
                continue
            try:
                meta = json.loads(meta_str)
            except (json.JSONDecodeError, TypeError):
                continue
            aid = meta.get("agent_id")
            if aid and aid != "default":
                conn.execute(
                    "UPDATE sessions SET agent_id = ? WHERE session_id = ?",
                    (aid, row[0]),
                )
        conn.commit()

    def _migrate_agent_messages_table(self, conn: sqlite3.Connection) -> None:
        """为 agent_messages 表补充新增列（兼容旧库）。"""
        cursor = conn.execute("PRAGMA table_info(agent_messages)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        migrations = [
            ("active_turn_id", "ALTER TABLE agent_messages ADD COLUMN active_turn_id TEXT"),
            (
                "attempt_count",
                "ALTER TABLE agent_messages ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 1",
            ),
            (
                "max_attempts",
                "ALTER TABLE agent_messages ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 1",
            ),
            ("timeout_seconds", "ALTER TABLE agent_messages ADD COLUMN timeout_seconds REAL"),
        ]
        for col, sql in migrations:
            if col not in existing_cols:
                conn.execute(sql)
        conn.commit()

    def _migrate_cron_runs_table(self, conn: sqlite3.Connection) -> None:
        """为 cron_runs 表补充 job_name / job_text 冗余列（兼容旧库）。"""
        cursor = conn.execute("PRAGMA table_info(cron_runs)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        for col, sql in [
            ("job_name", "ALTER TABLE cron_runs ADD COLUMN job_name TEXT"),
            ("job_text", "ALTER TABLE cron_runs ADD COLUMN job_text TEXT"),
        ]:
            if col not in existing_cols:
                conn.execute(sql)
        conn.commit()

    async def get_session_meta(self, session_id: str) -> dict[str, Any] | None:
        """获取会话的 meta 信息（含 agent_id 等）"""
        conn = self._conn()
        row = conn.execute("SELECT meta FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接
        if not row or not row[0]:
            return None
        return json.loads(row[0])

    # ---------- Messages 表操作 ----------

    async def save_message(
        self,
        session_id: str,
        turn_id: str,
        role: str,
        content: str | None = None,
        tool_calls: str | None = None,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
    ) -> None:
        """保存单条消息到 messages 表"""
        await asyncio.to_thread(
            self._sync_save_message,
            session_id, turn_id, role, content, tool_calls, tool_call_id, tool_name,
        )

    def _sync_save_message(
        self,
        session_id: str,
        turn_id: str,
        role: str,
        content: str | None,
        tool_calls: str | None,
        tool_call_id: str | None,
        tool_name: str | None,
    ) -> None:
        conn = self._conn()
        conn.execute(
            """INSERT INTO messages (session_id, turn_id, role, content, tool_calls, tool_call_id, tool_name, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, turn_id, role, content, tool_calls, tool_call_id, tool_name, time.time()),
        )
        conn.commit()

    async def get_session_messages(self, session_id: str) -> list[dict[str, Any]]:
        """获取会话的所有消息（按时间排序），返回 LLM 消息格式"""
        conn = self._conn()
        rows = conn.execute(
            "SELECT role, content, tool_calls, tool_call_id, tool_name FROM messages WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接
        messages: list[dict[str, Any]] = []
        for row in rows:
            msg: dict[str, Any] = {"role": row[0]}
            if row[1] is not None:
                msg["content"] = row[1]
            if row[2] is not None:
                msg["tool_calls"] = json.loads(row[2])
            if row[3] is not None:
                msg["tool_call_id"] = row[3]
            if row[4] is not None:
                msg["name"] = row[4]
            messages.append(msg)
        return messages

    async def update_session_info(
        self,
        session_id: str,
        channel: str | None = None,
        model: str | None = None,
    ) -> None:
        """更新会话的 channel 和 model 信息"""
        conn = self._conn()
        if channel is not None:
            conn.execute("UPDATE sessions SET channel = ? WHERE session_id = ?", (channel, session_id))
        if model is not None:
            conn.execute("UPDATE sessions SET model = ? WHERE session_id = ?", (model, session_id))
        conn.commit()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接

    async def increment_message_count(self, session_id: str) -> None:
        """递增会话消息计数"""
        await asyncio.to_thread(self._sync_increment_message_count, session_id)

    def _sync_increment_message_count(self, session_id: str) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE sessions SET message_count = COALESCE(message_count, 0) + 1 WHERE session_id = ?",
            (session_id,),
        )
        conn.commit()

    async def delete_session_cascade(self, session_id: str) -> None:
        """级联删除会话及关联的 turns, messages, events"""
        conn = self._conn()
        conn.execute(
            "DELETE FROM agent_messages WHERE parent_session_id = ? OR child_session_id = ?",
            (session_id, session_id),
        )
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM turns WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接

    # ---------- Agent Messages 表操作 ----------

    async def save_message_record(self, record: MessageRecord) -> None:
        """保存 Agent-to-Agent 消息记录。"""
        conn = self._conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO agent_messages (
                id, parent_session_id, parent_turn_id, parent_tool_call_id,
                child_session_id, target_id, status, mode, message,
                result, error, depth, pingpong_count, active_turn_id,
                attempt_count, max_attempts, timeout_seconds, created_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.parent_session_id,
                record.parent_turn_id,
                record.parent_tool_call_id,
                record.child_session_id,
                record.target_id,
                record.status,
                record.mode,
                record.message,
                record.result,
                record.error,
                record.depth,
                record.pingpong_count,
                record.active_turn_id,
                record.attempt_count,
                record.max_attempts,
                record.timeout_seconds,
                record.created_at,
                record.completed_at,
            ),
        )
        conn.commit()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接

    async def update_message_record(self, record: MessageRecord) -> None:
        """更新 Agent-to-Agent 消息记录。"""
        await self.save_message_record(record)

    async def get_message_record(self, record_id: str) -> MessageRecord | None:
        """按记录 ID 查询 Agent-to-Agent 消息记录。"""
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM agent_messages WHERE id = ?",
            (record_id,),
        ).fetchone()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接
        if not row:
            return None
        return MessageRecord.from_mapping(dict(row))

    async def get_message_record_by_child_session(
        self,
        child_session_id: str,
    ) -> MessageRecord | None:
        """按子会话 ID 查询最新一条 Agent-to-Agent 消息记录。"""
        conn = self._conn()
        row = conn.execute(
            """
            SELECT * FROM agent_messages
            WHERE child_session_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (child_session_id,),
        ).fetchone()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接
        if not row:
            return None
        return MessageRecord.from_mapping(dict(row))

    async def list_active_message_records(
        self,
        parent_session_id: str,
    ) -> list[MessageRecord]:
        """查询父会话下仍在运行中的 Agent-to-Agent 消息记录。"""
        conn = self._conn()
        rows = conn.execute(
            """
            SELECT * FROM agent_messages
            WHERE parent_session_id = ?
              AND status IN ('pending', 'running', 'retrying')
            ORDER BY created_at DESC
            """,
            (parent_session_id,),
        ).fetchall()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接
        return [MessageRecord.from_mapping(dict(row)) for row in rows]

    async def prune_sessions(self, max_age_days: int = 30) -> int:
        """删除超期未活跃的会话及关联数据，返回删除数量"""
        cutoff = time.time() - max_age_days * 86400
        conn = self._conn()
        rows = conn.execute(
            "SELECT session_id FROM sessions WHERE last_active < ?", (cutoff,)
        ).fetchall()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接
        count = 0
        for row in rows:
            await self.delete_session_cascade(row[0])
            count += 1
        return count

    async def cap_sessions(self, max_count: int = 500) -> int:
        """限制会话总数，淘汰最旧的，返回删除数量"""
        conn = self._conn()
        total = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        if total <= max_count:
            conn.close()
            self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接
            return 0
        overflow = total - max_count
        rows = conn.execute(
            "SELECT session_id FROM sessions ORDER BY last_active ASC LIMIT ?", (overflow,)
        ).fetchall()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接
        count = 0
        for row in rows:
            await self.delete_session_cascade(row[0])
            count += 1
        return count

    # ---------- Cron Jobs 表操作 ----------

    async def create_cron_job(self, job_data: dict[str, Any]) -> None:
        """插入一条 cron_jobs 记录"""
        conn = self._conn()
        conn.execute(
            """INSERT INTO cron_jobs (id, name, description, schedule_json, session_target,
               wake_mode, payload_json, delivery_json, enabled, delete_after_run,
               created_at_ms, updated_at_ms, next_run_at_ms, running_at_ms,
               last_run_at_ms, last_run_status, last_error, last_duration_ms, consecutive_errors)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_data["id"], job_data.get("name"), job_data.get("description"),
                job_data["schedule_json"], job_data.get("session_target", "isolated"),
                job_data.get("wake_mode", "now"), job_data["payload_json"],
                job_data.get("delivery_json"), job_data.get("enabled", 1),
                job_data.get("delete_after_run"), job_data["created_at_ms"],
                job_data["updated_at_ms"], job_data.get("next_run_at_ms"),
                job_data.get("running_at_ms"), job_data.get("last_run_at_ms"),
                job_data.get("last_run_status"), job_data.get("last_error"),
                job_data.get("last_duration_ms"), job_data.get("consecutive_errors", 0),
            ),
        )
        conn.commit()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接

    async def get_cron_job(self, job_id: str) -> dict[str, Any] | None:
        """按 ID 查询单条 cron job"""
        conn = self._conn()
        row = conn.execute("SELECT * FROM cron_jobs WHERE id = ?", (job_id,)).fetchone()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接
        return dict(row) if row else None

    async def list_cron_jobs(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        """返回所有 cron jobs"""
        conn = self._conn()
        if enabled_only:
            rows = conn.execute("SELECT * FROM cron_jobs WHERE enabled = 1 ORDER BY created_at_ms").fetchall()
        else:
            rows = conn.execute("SELECT * FROM cron_jobs ORDER BY created_at_ms").fetchall()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接
        return [dict(row) for row in rows]

    async def update_cron_job(self, job_id: str, updates: dict[str, Any]) -> None:
        """更新 cron job 的指定字段"""
        if not updates:
            return
        set_parts = [f"{k} = ?" for k in updates]
        values = list(updates.values()) + [job_id]
        conn = self._conn()
        conn.execute(f"UPDATE cron_jobs SET {', '.join(set_parts)} WHERE id = ?", values)
        conn.commit()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接

    async def delete_cron_job(self, job_id: str, *, keep_runs: bool = False) -> None:
        """删除 cron job。keep_runs=True 时保留 runs 历史（用于自动删除场景）。"""
        conn = self._conn()
        if not keep_runs:
            conn.execute("DELETE FROM cron_runs WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM cron_jobs WHERE id = ?", (job_id,))
        conn.commit()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接

    async def get_runnable_cron_jobs(self, now_ms: int) -> list[dict[str, Any]]:
        """返回到期且未在执行中的 enabled jobs"""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM cron_jobs WHERE enabled = 1 AND running_at_ms IS NULL AND next_run_at_ms <= ?",
            (now_ms,),
        ).fetchall()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接
        return [dict(row) for row in rows]

    async def update_cron_job_state(self, job_id: str, state_updates: dict[str, Any]) -> None:
        """更新 job 的运行状态字段"""
        await self.update_cron_job(job_id, state_updates)

    async def clear_stale_cron_running(self) -> None:
        """启动时清除所有 running_at_ms 残留（上次异常退出）"""
        conn = self._conn()
        conn.execute("UPDATE cron_jobs SET running_at_ms = NULL WHERE running_at_ms IS NOT NULL")
        conn.commit()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接

    # ---------- Cron Runs 表操作 ----------

    async def insert_cron_run(self, run_data: dict[str, Any]) -> int:
        """插入一条 cron_runs 记录，返回自增 ID"""
        conn = self._conn()
        cursor = conn.execute(
            """INSERT INTO cron_runs (job_id, started_at_ms, ended_at_ms, status, error,
               duration_ms, session_id, delivery_status, job_name, job_text, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_data["job_id"], run_data["started_at_ms"],
                run_data.get("ended_at_ms"), run_data.get("status"),
                run_data.get("error"), run_data.get("duration_ms"),
                run_data.get("session_id"), run_data.get("delivery_status"),
                run_data.get("job_name"), run_data.get("job_text"),
                run_data["created_at"],
            ),
        )
        run_id = cursor.lastrowid
        conn.commit()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接
        return run_id

    async def update_cron_run(self, run_id: int, updates: dict[str, Any]) -> None:
        """更新 cron_runs 记录"""
        if not updates:
            return
        set_parts = [f"{k} = ?" for k in updates]
        values = list(updates.values()) + [run_id]
        conn = self._conn()
        conn.execute(f"UPDATE cron_runs SET {', '.join(set_parts)} WHERE id = ?", values)
        conn.commit()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接

    async def list_cron_runs(self, job_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """按 started_at_ms 倒序列出 job 运行历史。"""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM cron_runs WHERE job_id = ? ORDER BY started_at_ms DESC LIMIT ?",
            (job_id, limit),
        ).fetchall()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接
        return [dict(row) for row in rows]

    async def list_all_cron_runs(self, limit: int = 50, status: str | None = None) -> list[dict[str, Any]]:
        """跨所有 job 列出 cron_runs，并 JOIN cron_jobs 获取 job 名称和 payload。"""
        conn = self._conn()
        sql = """
            SELECT r.*, j.name AS joined_job_name, j.payload_json
            FROM cron_runs r
            LEFT JOIN cron_jobs j ON r.job_id = j.id
        """
        params: list[Any] = []
        if status:
            sql += " WHERE r.status = ?"
            params.append(status)
        sql += " ORDER BY r.started_at_ms DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接
        return [dict(row) for row in rows]

    # ---------- Proactive Jobs 表操作 ----------

    async def create_proactive_job(self, row: dict[str, Any]) -> None:
        """插入一条 proactive_jobs 记录"""
        now_ms = int(time.time() * 1000)
        conn = self._conn()
        conn.execute(
            """INSERT INTO proactive_jobs (id, agent_id, name, enabled, trigger_json,
               task_json, delivery_json, safety_json, state_json, source,
               created_at_ms, updated_at_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                row["id"], row.get("agent_id", "proactive-agent"), row["name"],
                row.get("enabled", 1), row["trigger_json"], row["task_json"],
                row["delivery_json"], row["safety_json"],
                row.get("state_json", "{}"), row.get("source", "config"),
                row.get("created_at_ms", now_ms), row.get("updated_at_ms", now_ms),
            ),
        )
        conn.commit()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接

    async def get_proactive_job(self, job_id: str) -> dict[str, Any] | None:
        """按 ID 查询单条 proactive job"""
        conn = self._conn()
        row = conn.execute("SELECT * FROM proactive_jobs WHERE id = ?", (job_id,)).fetchone()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接
        return dict(row) if row else None

    async def list_proactive_jobs(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        """返回所有 proactive jobs"""
        conn = self._conn()
        if enabled_only:
            rows = conn.execute(
                "SELECT * FROM proactive_jobs WHERE enabled = 1 ORDER BY created_at_ms"
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM proactive_jobs ORDER BY created_at_ms").fetchall()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接
        return [dict(row) for row in rows]

    async def update_proactive_job(self, job_id: str, updates: dict[str, Any]) -> None:
        """更新 proactive job 的指定字段"""
        if not updates:
            return
        set_parts = [f"{k} = ?" for k in updates]
        values = list(updates.values()) + [job_id]
        conn = self._conn()
        conn.execute(f"UPDATE proactive_jobs SET {', '.join(set_parts)} WHERE id = ?", values)
        conn.commit()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接

    async def delete_proactive_job(self, job_id: str) -> None:
        """删除 proactive job 及其 runs"""
        conn = self._conn()
        conn.execute("DELETE FROM proactive_runs WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM proactive_jobs WHERE id = ?", (job_id,))
        conn.commit()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接

    # ---------- Proactive Runs 表操作 ----------

    async def create_proactive_run(self, row: dict[str, Any]) -> None:
        """插入一条 proactive_runs 记录"""
        conn = self._conn()
        conn.execute(
            """INSERT INTO proactive_runs (id, job_id, session_id, status, triggered_by,
               started_at_ms, completed_at_ms, result_summary, error_message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                row["id"], row["job_id"], row.get("session_id"),
                row["status"], row["triggered_by"], row["started_at_ms"],
                row.get("completed_at_ms"), row.get("result_summary"),
                row.get("error_message"),
            ),
        )
        conn.commit()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接

    async def update_proactive_run(self, run_id: str, updates: dict[str, Any]) -> None:
        """更新 proactive_runs 记录"""
        if not updates:
            return
        set_parts = [f"{k} = ?" for k in updates]
        values = list(updates.values()) + [run_id]
        conn = self._conn()
        conn.execute(f"UPDATE proactive_runs SET {', '.join(set_parts)} WHERE id = ?", values)
        conn.commit()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接

    async def list_proactive_runs(self, job_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """按 started_at_ms 倒序列出 job 运行历史"""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM proactive_runs WHERE job_id = ? ORDER BY started_at_ms DESC LIMIT ?",
            (job_id, limit),
        ).fetchall()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接
        return [dict(row) for row in rows]

    async def get_proactive_run(self, run_id: str) -> dict[str, Any] | None:
        """按 ID 查询单条 proactive run"""
        conn = self._conn()
        row = conn.execute("SELECT * FROM proactive_runs WHERE id = ?", (run_id,)).fetchone()
        conn.close()
        self._local.conn = None  # 关闭后清除缓存，避免下次 _conn() 返回已关闭连接
        return dict(row) if row else None
