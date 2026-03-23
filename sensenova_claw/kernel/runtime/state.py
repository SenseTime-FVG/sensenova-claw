from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from sensenova_claw.adapters.storage.repository import Repository


@dataclass
class TurnState:
    turn_id: str
    user_input: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    pending_tool_calls: set[str] = field(default_factory=set)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    final_response: str = ""
    history_offset: int = 0  # 本轮新消息在 messages 中的起始索引（跳过 system + 旧历史）


class SessionStateStore:
    def __init__(self):
        self._turns: dict[tuple[str, str], TurnState] = {}
        self._latest_turn: dict[str, str] = {}
        self._session_history: dict[str, list[dict[str, Any]]] = {}
        self._session_first_turn: dict[str, bool] = {}  # 记录是否是会话的第一轮对话
        self._cancelled_turns: set[tuple[str, str]] = set()

    def set_turn(self, session_id: str, state: TurnState) -> None:
        self._turns[(session_id, state.turn_id)] = state
        self._latest_turn[session_id] = state.turn_id
        self.clear_turn_cancelled(session_id, state.turn_id)

    def get_turn(self, session_id: str, turn_id: str) -> TurnState | None:
        return self._turns.get((session_id, turn_id))

    def latest_turn(self, session_id: str) -> TurnState | None:
        turn_id = self._latest_turn.get(session_id)
        if not turn_id:
            return None
        return self._turns.get((session_id, turn_id))

    def mark_turn_cancelled(self, session_id: str, turn_id: str) -> None:
        self._cancelled_turns.add((session_id, turn_id))

    def is_turn_cancelled(self, session_id: str, turn_id: str) -> bool:
        return (session_id, turn_id) in self._cancelled_turns

    def clear_turn_cancelled(self, session_id: str, turn_id: str) -> None:
        self._cancelled_turns.discard((session_id, turn_id))

    def get_session_history(self, session_id: str) -> list[dict[str, Any]]:
        return self._session_history.get(session_id, [])

    def append_to_history(self, session_id: str, messages: list[dict[str, Any]]) -> None:
        if session_id not in self._session_history:
            self._session_history[session_id] = []
        self._session_history[session_id].extend(messages)

    def replace_history(self, session_id: str, history: list[dict[str, Any]]) -> None:
        """替换会话历史（用于上下文压缩后更新）"""
        self._session_history[session_id] = history

    def is_first_turn(self, session_id: str) -> bool:
        """检查是否是会话的第一轮对话"""
        return session_id not in self._session_first_turn

    def mark_first_turn_done(self, session_id: str) -> None:
        """标记第一轮对话已完成"""
        self._session_first_turn[session_id] = True

    async def load_session_history(self, session_id: str, repo: Repository) -> list[dict[str, Any]]:
        """从 SQLite 加载会话历史到内存（惰性加载）"""
        if session_id in self._session_history:
            return self._session_history[session_id]
        messages = await repo.get_session_messages(session_id)
        self._session_history[session_id] = messages
        return messages
