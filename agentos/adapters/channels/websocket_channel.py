from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import (
    AGENT_STEP_COMPLETED,
    AGENT_STEP_STARTED,
    CRON_DELIVERY_REQUESTED,
    ERROR_RAISED,
    LLM_CALL_COMPLETED,
    LLM_CALL_REQUESTED,
    TOOL_CALL_REQUESTED,
    TOOL_CALL_RESULT,
    TOOL_CONFIRMATION_REQUESTED,
    USER_QUESTION_ASKED,
)
from agentos.adapters.channels.base import Channel

AGENT_UPDATE_TITLE_COMPLETED = "agent.update_title_completed"

logger = logging.getLogger(__name__)


class WebSocketChannel(Channel):
    """WebSocket Channel 实现"""

    def __init__(self, channel_id: str = "websocket"):
        self._channel_id = channel_id
        self._connections: set[WebSocket] = set()
        self._session_bindings: dict[str, set[WebSocket]] = {}

    def get_channel_id(self) -> str:
        return self._channel_id

    async def start(self) -> None:
        logger.info(f"WebSocketChannel {self._channel_id} started")

    async def stop(self) -> None:
        logger.info(f"WebSocketChannel {self._channel_id} stopped")

    async def connect(self, websocket: WebSocket) -> None:
        """接受 WebSocket 连接"""
        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """断开 WebSocket 连接"""
        self._connections.discard(websocket)
        for conns in self._session_bindings.values():
            conns.discard(websocket)

    def bind_session(self, session_id: str, websocket: WebSocket) -> None:
        """绑定 session 到 WebSocket"""
        self._session_bindings.setdefault(session_id, set()).add(websocket)

    async def send_json(self, websocket: WebSocket, data: dict[str, Any]) -> None:
        """发送 JSON 数据到指定 WebSocket"""
        await websocket.send_json(data)

    async def send_event(self, event: EventEnvelope) -> None:
        """接收来自 Gateway 的事件并发送给用户"""
        mapped = self._map(event)
        if not mapped:
            return

        # cron 投递事件广播到所有已连接客户端（不按 session 过滤）
        if event.type == CRON_DELIVERY_REQUESTED:
            for ws in list(self._connections):
                try:
                    await ws.send_json(mapped)
                except Exception:
                    self.disconnect(ws)
            return

        session_id = event.session_id
        websockets = self._session_bindings.get(session_id, set())

        for ws in list(websockets):
            try:
                await ws.send_json(mapped)
            except Exception:
                self.disconnect(ws)

    def _map(self, event: EventEnvelope) -> dict[str, Any] | None:
        """将事件映射为前端消息格式"""
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
        if event.type == LLM_CALL_COMPLETED:
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
        if event.type == CRON_DELIVERY_REQUESTED:
            return {
                "type": "notification",
                "session_id": event.session_id,
                "payload": {
                    "text": event.payload.get("text", ""),
                    "source": "cron",
                    "job_id": event.payload.get("job_id"),
                    "job_name": event.payload.get("job_name"),
                },
                "timestamp": event.ts,
            }
        # v1.4: 工具确认请求
        if event.type == TOOL_CONFIRMATION_REQUESTED:
            return {
                "type": "tool_confirmation_requested",
                "session_id": event.session_id,
                "payload": {
                    "tool_call_id": event.payload.get("tool_call_id"),
                    "tool_name": event.payload.get("tool_name"),
                    "arguments": event.payload.get("arguments", {}),
                    "risk_level": event.payload.get("risk_level", "high"),
                },
                "timestamp": event.ts,
            }
        # 用户问答请求
        if event.type == USER_QUESTION_ASKED:
            return {
                "type": "user_question_asked",
                "session_id": event.session_id,
                "payload": {
                    "question_id": event.payload.get("question_id"),
                    "question": event.payload.get("question"),
                    "options": event.payload.get("options"),
                    "multi_select": event.payload.get("multi_select", False),
                    "timeout": event.payload.get("timeout", 300),
                },
                "timestamp": event.ts,
            }
        return None
