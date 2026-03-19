"""按 Agent 分目录的 Session JSONL 写入器

文件布局：
  {base_dir}/
    {agent_id}/
      sessions/
        {session_id}.jsonl

每行一个 JSON 对象，格式：
  {"ts": 1710000000.0, "session_id": "...", "turn_id": "...", "role": "user", "content": "...", ...}
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SessionJsonlWriter:
    """将消息以 JSONL 格式追加写入磁盘，按 agent_id 分目录、session_id 分文件。"""

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)

    def _session_path(self, agent_id: str, session_id: str) -> Path:
        safe_agent = agent_id.replace("/", "_").replace("\\", "_") or "default"
        safe_session = session_id.replace("/", "_").replace("\\", "_")
        return self.base_dir / safe_agent / "sessions" / f"{safe_session}.jsonl"

    def append(
        self,
        agent_id: str,
        session_id: str,
        turn_id: str,
        msg: dict[str, Any],
    ) -> None:
        """追加一条消息到对应 session 的 JSONL 文件（同步 IO，单次写入很小）。"""
        path = self._session_path(agent_id, session_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        record: dict[str, Any] = {
            "ts": time.time(),
            "session_id": session_id,
            "turn_id": turn_id,
            "role": msg.get("role", ""),
        }
        if msg.get("content") is not None:
            record["content"] = msg["content"]
        if msg.get("tool_calls"):
            record["tool_calls"] = msg["tool_calls"]
        if msg.get("tool_call_id"):
            record["tool_call_id"] = msg["tool_call_id"]
        if msg.get("name"):
            record["name"] = msg["name"]

        line = json.dumps(record, ensure_ascii=False)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
