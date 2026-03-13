from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any

from fastapi import WebSocket

from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import AGENT_STEP_COMPLETED, AGENT_STEP_STARTED, ERROR_RAISED, LLM_CALL_COMPLETED, LLM_CALL_REQUESTED, LLM_CALL_RESULT, TOOL_CALL_REQUESTED, TOOL_CALL_RESULT
from agentos.kernel.runtime.publisher import EventPublisher

AGENT_UPDATE_TITLE_COMPLETED = "agent.update_title_completed"

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.connections: set[WebSocket] = set()
        self.session_bindings: dict[str, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.connections.discard(websocket)
        for _, conns in self.session_bindings.items():
            conns.discard(websocket)

    def bind_session(self, session_id: str, websocket: WebSocket) -> None:
        self.session_bindings.setdefault(session_id, set()).add(websocket)

    async def send_json(self, websocket: WebSocket, data: dict[str, Any]) -> None:
        await websocket.send_json(data)

    async def send_to_session(self, session_id: str, data: dict[str, Any]) -> None:
        for ws in list(self.session_bindings.get(session_id, set())):
            try:
                await ws.send_json(data)
            except Exception:  # noqa: BLE001
                self.disconnect(ws)


class WebSocketForwarder:
    def __init__(self, publisher: EventPublisher, manager: ConnectionManager):
        self.publisher = publisher
        self.manager = manager
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _loop(self) -> None:
        async for event in self.publisher.bus.subscribe():
            mapped = self._map(event)
            if mapped:
                await self.manager.send_to_session(event.session_id, mapped)

    def _map(self, event: EventEnvelope) -> dict[str, Any] | None:
        if event.type == AGENT_STEP_STARTED:
            return {
                "type": "agent_thinking",
                "session_id": event.session_id,
                "payload": event.payload,
                "timestamp": event.ts,
            }
        if event.type == LLM_CALL_REQUESTED:
            return {
                "type": "agent_thinking",
                "session_id": event.session_id,
                "payload": {"step_type": "llm_call", "description": "正在调用模型..."},
                "timestamp": event.ts,
            }
        if event.type == LLM_CALL_RESULT:
            # 发送LLM结果给前端
            response = event.payload.get("response", {})
            return {
                "type": "llm_result",
                "session_id": event.session_id,
                "payload": {
                    "llm_call_id": event.payload.get("llm_call_id"),
                    "content": response.get("content", ""),
                    "tool_calls": response.get("tool_calls", []),
                    "usage": event.payload.get("usage", {}),
                    "finish_reason": event.payload.get("finish_reason", "stop"),
                },
                "timestamp": event.ts,
            }
        if event.type == LLM_CALL_COMPLETED:
            # LLM 调用完成，不发送内容
            return None
        if event.type == TOOL_CALL_REQUESTED:
            return {
                "type": "tool_execution",
                "session_id": event.session_id,
                "payload": {
                    "tool_call_id": event.payload.get("tool_call_id"),
                    "tool_name": event.payload.get("tool_name"),
                    "status": "running",
                    "arguments": event.payload.get("arguments", {}),
                },
                "timestamp": event.ts,
            }
        if event.type == TOOL_CALL_RESULT:
            return {
                "type": "tool_result",
                "session_id": event.session_id,
                "payload": {
                    "tool_call_id": event.payload.get("tool_call_id"),
                    "tool_name": event.payload.get("tool_name"),
                    "result": event.payload.get("result"),
                    "success": event.payload.get("success", False),
                    "error": event.payload.get("error", ""),
                },
                "timestamp": event.ts,
            }
        if event.type == AGENT_STEP_COMPLETED:
            return {
                "type": "turn_completed",
                "session_id": event.session_id,
                "payload": {
                    "turn_id": event.turn_id,
                    "final_response": event.payload.get("result", {}).get("content", ""),
                },
                "timestamp": event.ts,
            }
        if event.type == ERROR_RAISED:
            return {
                "type": "error",
                "session_id": event.session_id,
                "payload": {
                    "error_type": event.payload.get("error_type"),
                    "message": event.payload.get("error_message"),
                    "details": event.payload.get("context", {}),
                },
                "timestamp": event.ts,
            }
        if event.type == AGENT_UPDATE_TITLE_COMPLETED:
            return {
                "type": "title_updated",
                "session_id": event.session_id,
                "payload": {
                    "title": event.payload.get("title"),
                    "success": event.payload.get("success"),
                },
                "timestamp": event.ts,
            }
        return None


def now_ts() -> float:
    return time.time()
