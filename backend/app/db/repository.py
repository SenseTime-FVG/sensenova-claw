from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from app.core.config import config
from app.events.envelope import EventEnvelope

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
