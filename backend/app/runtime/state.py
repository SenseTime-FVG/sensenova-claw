from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TurnState:
    turn_id: str
    user_input: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    pending_tool_calls: set[str] = field(default_factory=set)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    final_response: str = ""


class SessionStateStore:
    def __init__(self):
        self._turns: dict[tuple[str, str], TurnState] = {}
        self._latest_turn: dict[str, str] = {}

    def set_turn(self, session_id: str, state: TurnState) -> None:
        self._turns[(session_id, state.turn_id)] = state
        self._latest_turn[session_id] = state.turn_id

    def get_turn(self, session_id: str, turn_id: str) -> TurnState | None:
        return self._turns.get((session_id, turn_id))

    def latest_turn(self, session_id: str) -> TurnState | None:
        turn_id = self._latest_turn.get(session_id)
        if not turn_id:
            return None
        return self._turns.get((session_id, turn_id))
