from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass
class MessageRecord:
    """Agent-to-Agent 消息记录。"""

    id: str
    parent_session_id: str
    parent_turn_id: str | None
    parent_tool_call_id: str | None
    child_session_id: str
    target_id: str
    status: str
    mode: str
    message: str
    result: str | None
    error: str | None
    depth: int
    pingpong_count: int
    created_at: float
    active_turn_id: str | None = None
    attempt_count: int = 1
    max_attempts: int = 1
    timeout_seconds: float | None = None
    completed_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "parent_session_id": self.parent_session_id,
            "parent_turn_id": self.parent_turn_id,
            "parent_tool_call_id": self.parent_tool_call_id,
            "child_session_id": self.child_session_id,
            "target_id": self.target_id,
            "status": self.status,
            "mode": self.mode,
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "depth": self.depth,
            "pingpong_count": self.pingpong_count,
            "active_turn_id": self.active_turn_id,
            "attempt_count": self.attempt_count,
            "max_attempts": self.max_attempts,
            "timeout_seconds": self.timeout_seconds,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> MessageRecord:
        return cls(
            id=str(data["id"]),
            parent_session_id=str(data["parent_session_id"]),
            parent_turn_id=data.get("parent_turn_id"),
            parent_tool_call_id=data.get("parent_tool_call_id"),
            child_session_id=str(data["child_session_id"]),
            target_id=str(data["target_id"]),
            status=str(data["status"]),
            mode=str(data["mode"]),
            message=str(data["message"]),
            result=data.get("result"),
            error=data.get("error"),
            depth=int(data.get("depth", 0)),
            pingpong_count=int(data.get("pingpong_count", 0)),
            active_turn_id=data.get("active_turn_id"),
            attempt_count=int(data.get("attempt_count", 1)),
            max_attempts=int(data.get("max_attempts", 1)),
            timeout_seconds=(
                float(data["timeout_seconds"])
                if data.get("timeout_seconds") is not None
                else None
            ),
            created_at=float(data.get("created_at", 0.0)),
            completed_at=data.get("completed_at"),
        )
