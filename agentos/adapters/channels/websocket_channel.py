from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

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
)
from agentos.adapters.channels.base import Channel

AGENT_UPDATE_TITLE_COMPLETED = "agent.update_title_completed"

logger = logging.getLogger(__name__)


class WebSocketChannel(Channel):
    """WebSocket Channel：协议适配 + 认证 + 消息循环"""

    def __init__(self, channel_id: str = "websocket", auth_service=None):
        super().__init__()
        self._channel_id = channel_id
        self._connections: set[WebSocket] = set()
        self._session_bindings: dict[str, set[WebSocket]] = {}
        self._auth_service = auth_service

    def get_channel_id(self) -> str:
        return self._channel_id

    async def start(self) -> None:
        logger.info(f"WebSocketChannel {self._channel_id} started")

    async def stop(self) -> None:
        logger.info(f"WebSocketChannel {self._channel_id} stopped")

    # ── 连接管理 ──────────────────────────────────────

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

    # ── 连接生命周期（认证 + 消息循环） ───────────────

    async def handle_connection(self, websocket: WebSocket) -> None:
        """处理单个 WebSocket 连接的完整生命周期"""
        from agentos.platform.config.config import config
        from agentos.platform.security.middleware import verify_websocket

        # 认证
        auth_enabled = config.get("security.auth_enabled", False)
        if auth_enabled and self._auth_service:
            if not verify_websocket(websocket, self._auth_service):
                logger.warning("WebSocket connection rejected: invalid or missing token")
                await websocket.close(code=1008, reason="Invalid or missing token")
                return

        await self.connect(websocket)
        logger.info("WebSocket client connected")

        try:
            while True:
                message = await websocket.receive_json()
                await self._handle_message(websocket, message)
        except WebSocketDisconnect:
            self.disconnect(websocket)
        except Exception as exc:
            logger.exception("WebSocket connection error")
            self.disconnect(websocket)
            try:
                await self.send_json(websocket, {
                    "type": "error",
                    "payload": {
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                        "details": {},
                    },
                    "timestamp": time.time(),
                })
            except Exception:
                pass

    async def _handle_message(self, websocket: WebSocket, message: dict) -> None:
        """将 WS 消息翻译为 Gateway 方法调用"""
        msg_type = message.get("type")
        payload = message.get("payload", {})
        session_id = message.get("session_id")
        gw = self.gateway

        logger.info("Received WS message: %s", msg_type)

        if msg_type == "create_session":
            agent_id = payload.get("agent_id", "default")
            meta = payload.get("meta", {})
            result = await gw.create_session(agent_id=agent_id, meta=meta, channel_id=self._channel_id)
            sid = result["session_id"]
            self.bind_session(sid, websocket)
            await self.send_json(websocket, {
                "type": "session_created", "session_id": sid,
                "payload": {"created_at": result["created_at"]}, "timestamp": time.time(),
            })
            return

        if msg_type == "list_sessions":
            sessions = await gw.list_sessions(limit=int(payload.get("limit", 50)))
            await self.send_json(websocket, {
                "type": "sessions_list", "payload": {"sessions": sessions}, "timestamp": time.time(),
            })
            return

        if msg_type == "load_session":
            sid = payload.get("session_id")
            if sid:
                result = await gw.load_session(sid, channel_id=self._channel_id)
                self.bind_session(sid, websocket)
                await self.send_json(websocket, {
                    "type": "session_loaded", "session_id": sid,
                    "payload": {"events": result["events"]}, "timestamp": time.time(),
                })
            return

        if msg_type == "user_input":
            if not session_id:
                result = await gw.create_session(channel_id=self._channel_id)
                session_id = result["session_id"]
                self.bind_session(session_id, websocket)
                await self.send_json(websocket, {
                    "type": "session_created", "session_id": session_id,
                    "payload": {"created_at": result["created_at"]}, "timestamp": time.time(),
                })
            await gw.send_user_input(
                session_id=session_id,
                content=payload.get("content", ""),
                attachments=payload.get("attachments", []),
                context_files=payload.get("context_files", []),
                source="websocket",
            )
            return

        if msg_type == "cancel_turn":
            if session_id:
                await gw.cancel_turn(session_id, source="websocket")
            return

        if msg_type == "delete_session":
            sid = payload.get("session_id")
            if sid:
                try:
                    await gw.delete_session(sid)
                    self._session_bindings.pop(sid, None)
                    await self.send_json(websocket, {
                        "type": "session_deleted", "payload": {"session_id": sid}, "timestamp": time.time(),
                    })
                except Exception as e:
                    await self.send_json(websocket, {
                        "type": "error", "payload": {"message": f"删除会话失败: {e}"}, "timestamp": time.time(),
                    })
            return

        if msg_type == "rename_session":
            sid = payload.get("session_id") or session_id
            title = payload.get("title", "")
            if sid and title:
                try:
                    await gw.rename_session(sid, title)
                    await self.send_json(websocket, {
                        "type": "session_renamed", "payload": {"session_id": sid, "title": title},
                        "timestamp": time.time(),
                    })
                except Exception as e:
                    await self.send_json(websocket, {
                        "type": "error", "payload": {"message": f"重命名会话失败: {e}"}, "timestamp": time.time(),
                    })
            else:
                await self.send_json(websocket, {
                    "type": "error", "payload": {"message": "需要 session_id 和 title"}, "timestamp": time.time(),
                })
            return

        if msg_type == "list_agents":
            agents = await gw.list_agents()
            await self.send_json(websocket, {
                "type": "agents_list", "payload": {"agents": agents}, "timestamp": time.time(),
            })
            return

        if msg_type == "tool_confirmation_response":
            if session_id:
                await gw.confirm_tool(
                    session_id=session_id,
                    tool_call_id=payload.get("tool_call_id"),
                    approved=payload.get("approved", False),
                    source="websocket",
                )
            return

        if msg_type == "get_messages":
            sid = payload.get("session_id") or session_id
            messages = await gw.get_messages(sid) if sid else []
            await self.send_json(websocket, {
                "type": "messages_list", "payload": {"messages": messages}, "timestamp": time.time(),
            })
            return

        # 未知消息类型
        await self.send_json(websocket, {
            "type": "error",
            "payload": {"error_type": "InvalidMessage", "message": f"unsupported message type: {msg_type}"},
            "timestamp": time.time(),
        })

    # ── 事件映射（Gateway → 前端） ────────────────────

    async def send_event(self, event: EventEnvelope) -> None:
        """接收来自 Gateway 的事件并发送给用户"""
        mapped = self._map(event)
        if not mapped:
            return

        # cron 投递事件广播到所有已连接客户端
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
        return None
