"""QQ OneBot/NapCat runtime。"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import websockets

from .config import QQConfig
from .models import QQInboundMessage

logger = logging.getLogger(__name__)

QQMessageHandler = Callable[[QQInboundMessage], Awaitable[None]]


class QQOneBotRuntime:
    """基于 OneBot WebSocket + HTTP API 的最小 runtime。"""

    def __init__(self, config: QQConfig):
        self._config = config
        self._message_handler: QQMessageHandler | None = None
        self._recv_task: asyncio.Task | None = None
        self._ws = None
        self._sensenova_claw_status = {"status": "initialized", "error": None}

    def set_message_handler(self, handler: QQMessageHandler) -> None:
        self._message_handler = handler

    async def start(self) -> None:
        if not self._config.onebot.ws_url:
            raise RuntimeError("QQ OneBot ws_url is required")
        headers = {}
        if self._config.onebot.access_token:
            headers["Authorization"] = f"Bearer {self._config.onebot.access_token}"
        self._ws = await websockets.connect(self._config.onebot.ws_url, additional_headers=headers or None)
        self._recv_task = asyncio.create_task(self._recv_loop(), name="qq-onebot-recv")
        self._sensenova_claw_status = {"status": "connected", "error": None}

    async def stop(self) -> None:
        if self._recv_task is not None:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
            self._recv_task = None
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        self._sensenova_claw_status = {"status": "stopped", "error": None}

    async def send_text(self, target: str, text: str, *, reply_to_message_id: str | None = None) -> dict:
        api_base = self._config.onebot.api_base_url.rstrip("/")
        if not api_base:
            raise RuntimeError("QQ OneBot api_base_url is required")
        if ":" not in target:
            raise RuntimeError(f"Invalid OneBot target: {target}")

        target_type, target_id = target.split(":", 1)
        if target_type == "group":
            path = "/send_group_msg"
            payload: dict[str, Any] = {"group_id": int(target_id), "message": text}
        else:
            path = "/send_private_msg"
            payload = {"user_id": int(target_id), "message": text}

        if reply_to_message_id:
            payload["message"] = [{"type": "reply", "data": {"id": str(reply_to_message_id)}}, {"type": "text", "data": {"text": text}}]

        headers = {}
        if self._config.onebot.access_token:
            headers["Authorization"] = f"Bearer {self._config.onebot.access_token}"

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(f"{api_base}{path}", json=payload, headers=headers or None)
            response.raise_for_status()
            data = response.json()
        message_id = str((data or {}).get("data", {}).get("message_id", ""))
        return {"success": True, "message_id": message_id}

    async def _recv_loop(self) -> None:
        assert self._ws is not None
        while True:
            try:
                payload = await self._ws.recv()
                await self._handle_ws_payload(payload)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("QQ OneBot recv loop failed")
                self._sensenova_claw_status = {"status": "failed", "error": "recv loop failed"}
                await asyncio.sleep(1)

    async def _handle_ws_payload(self, payload: str | dict[str, Any]) -> None:
        data = json.loads(payload) if isinstance(payload, str) else payload
        if data.get("post_type") != "message":
            return
        inbound = self._normalize_event(data)
        if inbound is None or self._message_handler is None:
            return
        await self._message_handler(inbound)

    def _normalize_event(self, data: dict[str, Any]) -> QQInboundMessage | None:
        message_type = str(data.get("message_type", "")).strip()
        sender = data.get("sender") or {}
        sender_id = str(data.get("user_id", "")).strip()
        text = self._extract_text(data).strip()
        if not text:
            return None

        if message_type == "group":
            chat_type = "group"
            chat_id = str(data.get("group_id", "")).strip()
            target = f"group:{chat_id}"
        else:
            chat_type = "p2p"
            chat_id = sender_id
            target = f"user:{sender_id}"

        return QQInboundMessage(
            text=text,
            chat_type=chat_type,
            chat_id=chat_id,
            sender_id=sender_id,
            sender_name=str(sender.get("nickname", "")).strip(),
            message_id=str(data.get("message_id", "")).strip(),
            target=target,
            mentioned_bot=self._is_mentioned(data),
            raw_event=data,
        )

    def _extract_text(self, data: dict[str, Any]) -> str:
        segments = data.get("message")
        if isinstance(segments, list):
            parts: list[str] = []
            for segment in segments:
                if segment.get("type") == "text":
                    parts.append(str((segment.get("data") or {}).get("text", "")))
            if parts:
                return "".join(parts)
        return str(data.get("raw_message", "")).strip()

    def _is_mentioned(self, data: dict[str, Any]) -> bool:
        self_id = str(self._config.onebot.self_id or "").strip()
        if not self_id:
            return False
        for segment in data.get("message") or []:
            if segment.get("type") == "at" and str((segment.get("data") or {}).get("qq", "")).strip() == self_id:
                return True
        raw_message = str(data.get("raw_message", ""))
        return f"qq={self_id}" in raw_message

