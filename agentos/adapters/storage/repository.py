from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from agentos.platform.config.config import config
from agentos.kernel.events.envelope import EventEnvelope

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
    created_at REAL NOT NULL,
    FOREIGN KEY (job_id) REFERENCES cron_jobs(id)
);
CREATE INDEX IF NOT EXISTS idx_cron_runs_job ON cron_runs(job_id);
"""


class Repository:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path or config.get("system.database_path", "./SenseAssistant/agentos.db")).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    async def init(self) -> None:
        conn = self._conn()
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        self._migrate_sessions_table(conn)
        conn.close()

    async def create_session(self, session_id: str, meta: dict[str, Any] | None = None) -> None:
        now = time.time()
        conn = self._conn()
        conn.execute(
            "INSERT OR IGNORE INTO sessions (session_id, created_at, last_active, meta) VALUES (?, ?, ?, ?)",
            (session_id, now, now, json.dumps(meta or {}, ensure_ascii=False)),
        )
        conn.commit()
        conn.close()

    async def update_session_activity(self, session_id: str) -> None:
        conn = self._conn()
        conn.execute("UPDATE sessions SET last_active = ? WHERE session_id = ?", (time.time(), session_id))
        conn.commit()
        conn.close()

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

    async def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM sessions ORDER BY last_active DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    async def create_turn(self, turn_id: str, session_id: str, user_input: str) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO turns (turn_id, session_id, status, started_at, user_input) VALUES (?, ?, ?, ?, ?)",
            (turn_id, session_id, "started", time.time(), user_input),
        )
        conn.commit()
        conn.close()

    async def complete_turn(self, turn_id: str, agent_response: str) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE turns SET status = ?, ended_at = ?, agent_response = ? WHERE turn_id = ?",
            ("completed", time.time(), agent_response, turn_id),
        )
        conn.commit()
        conn.close()

    async def log_event(self, event: EventEnvelope) -> None:
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
        conn.close()

    async def get_session_events(self, session_id: str) -> list[dict[str, Any]]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM events WHERE session_id = ? ORDER BY timestamp", (session_id,)).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    async def get_session_turns(self, session_id: str) -> list[dict[str, Any]]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM turns WHERE session_id = ? ORDER BY started_at",
            (session_id,),
        ).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    # ---------- Sessions 表迁移 ----------

    def _migrate_sessions_table(self, conn: sqlite3.Connection) -> None:
        """为 sessions 表添加新列（如不存在）"""
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

    async def get_session_meta(self, session_id: str) -> dict[str, Any] | None:
        """获取会话的 meta 信息（含 agent_id 等）"""
        conn = self._conn()
        row = conn.execute("SELECT meta FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        conn.close()
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
        conn = self._conn()
        conn.execute(
            """INSERT INTO messages (session_id, turn_id, role, content, tool_calls, tool_call_id, tool_name, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, turn_id, role, content, tool_calls, tool_call_id, tool_name, time.time()),
        )
        conn.commit()
        conn.close()

    async def get_session_messages(self, session_id: str) -> list[dict[str, Any]]:
        """获取会话的所有消息（按时间排序），返回 LLM 消息格式"""
        conn = self._conn()
        rows = conn.execute(
            "SELECT role, content, tool_calls, tool_call_id, tool_name FROM messages WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        conn.close()
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

    async def increment_message_count(self, session_id: str) -> None:
        """递增会话消息计数"""
        conn = self._conn()
        conn.execute(
            "UPDATE sessions SET message_count = COALESCE(message_count, 0) + 1 WHERE session_id = ?",
            (session_id,),
        )
        conn.commit()
        conn.close()

    async def delete_session_cascade(self, session_id: str) -> None:
        """级联删除会话及关联的 turns, messages, events"""
        conn = self._conn()
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM turns WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()

    async def prune_sessions(self, max_age_days: int = 30) -> int:
        """删除超期未活跃的会话及关联数据，返回删除数量"""
        cutoff = time.time() - max_age_days * 86400
        conn = self._conn()
        rows = conn.execute(
            "SELECT session_id FROM sessions WHERE last_active < ?", (cutoff,)
        ).fetchall()
        conn.close()
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
            return 0
        overflow = total - max_count
        rows = conn.execute(
            "SELECT session_id FROM sessions ORDER BY last_active ASC LIMIT ?", (overflow,)
        ).fetchall()
        conn.close()
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

    async def get_cron_job(self, job_id: str) -> dict[str, Any] | None:
        """按 ID 查询单条 cron job"""
        conn = self._conn()
        row = conn.execute("SELECT * FROM cron_jobs WHERE id = ?", (job_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    async def list_cron_jobs(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        """返回所有 cron jobs"""
        conn = self._conn()
        if enabled_only:
            rows = conn.execute("SELECT * FROM cron_jobs WHERE enabled = 1 ORDER BY created_at_ms").fetchall()
        else:
            rows = conn.execute("SELECT * FROM cron_jobs ORDER BY created_at_ms").fetchall()
        conn.close()
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

    async def delete_cron_job(self, job_id: str) -> None:
        """删除 cron job 及其 runs 记录"""
        conn = self._conn()
        conn.execute("DELETE FROM cron_runs WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM cron_jobs WHERE id = ?", (job_id,))
        conn.commit()
        conn.close()

    async def get_runnable_cron_jobs(self, now_ms: int) -> list[dict[str, Any]]:
        """返回到期且未在执行中的 enabled jobs"""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM cron_jobs WHERE enabled = 1 AND running_at_ms IS NULL AND next_run_at_ms <= ?",
            (now_ms,),
        ).fetchall()
        conn.close()
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

    # ---------- Cron Runs 表操作 ----------

    async def insert_cron_run(self, run_data: dict[str, Any]) -> int:
        """插入一条 cron_runs 记录，返回自增 ID"""
        conn = self._conn()
        cursor = conn.execute(
            """INSERT INTO cron_runs (job_id, started_at_ms, ended_at_ms, status, error,
               duration_ms, session_id, delivery_status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_data["job_id"], run_data["started_at_ms"],
                run_data.get("ended_at_ms"), run_data.get("status"),
                run_data.get("error"), run_data.get("duration_ms"),
                run_data.get("session_id"), run_data.get("delivery_status"),
                run_data["created_at"],
            ),
        )
        run_id = cursor.lastrowid
        conn.commit()
        conn.close()
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
