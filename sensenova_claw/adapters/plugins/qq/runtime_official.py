"""QQ 官方开放平台 runtime。"""

from __future__ import annotations

import asyncio
import json
import logging
import platform
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import websockets

from .config import QQConfig
from .models import QQInboundMessage

logger = logging.getLogger(__name__)

QQMessageHandler = Callable[[QQInboundMessage], Awaitable[None]]


class QQOfficialRuntime:
    """基于 QQ 官方开放平台 HTTP/WebSocket 的最小 runtime。"""

    WS_DISPATCH = 0
    WS_HEARTBEAT = 1
    WS_IDENTIFY = 2
    WS_RESUME = 6
    WS_RECONNECT = 7
    WS_INVALID_SESSION = 9
    WS_HELLO = 10
    WS_HEARTBEAT_ACK = 11

    def __init__(self, config: QQConfig):
        self._config = config
        self._message_handler: QQMessageHandler | None = None
        self._gateway_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._ws = None
        self._access_token: str = ""
        self._token_expire_at: float = 0
        self._last_seq: int | None = None
        self._session_id: str = ""
        self._shard: list[int] = [0, 1]
        self._bot_user: dict[str, Any] = {}
        self._sensenova_claw_status = {"status": "initialized", "error": None}

    def set_message_handler(self, handler: QQMessageHandler) -> None:
        self._message_handler = handler

    async def start(self) -> None:
        self._sensenova_claw_status = {"status": "connecting", "error": None}
        await self._refresh_access_token()
        gateway = await self._fetch_gateway()
        self._ws = await websockets.connect(gateway)
        self._gateway_task = asyncio.create_task(self._recv_loop(), name="qq-official-recv")

    async def stop(self) -> None:
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        if self._gateway_task is not None:
            self._gateway_task.cancel()
            try:
                await self._gateway_task
            except asyncio.CancelledError:
                pass
            self._gateway_task = None
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        self._sensenova_claw_status = {"status": "stopped", "error": None}

    async def handle_event(self, payload: dict[str, Any]) -> None:
        inbound = self._normalize_event(payload)
        if inbound is None or self._message_handler is None:
            return
        await self._message_handler(inbound)

    async def send_text(self, target: str, text: str, *, reply_to_message_id: str | None = None) -> dict:
        headers = await self._build_headers()
        if ":" not in target:
            raise RuntimeError(f"Invalid QQ official target: {target}")

        target_type, target_id = target.split(":", 1)
        if target_type == "direct":
            path = f"/dms/{target_id}/messages"
        elif target_type == "channel":
            path = f"/channels/{target_id}/messages"
        else:
            path = f"/v2/groups/{target_id}/messages"

        payload: dict[str, Any] = {"content": text}
        if reply_to_message_id:
            payload["msg_id"] = reply_to_message_id

        async with httpx.AsyncClient(base_url=self._api_base_url(), timeout=20) as client:
            response = await client.post(path, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        return {"success": True, "message_id": str((data or {}).get("id", ""))}

    async def _recv_loop(self) -> None:
        assert self._ws is not None
        while True:
            try:
                raw_payload = await self._ws.recv()
                payload = json.loads(raw_payload)
                await self._handle_gateway_payload(payload)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("QQ official recv loop failed")
                self._sensenova_claw_status = {"status": "failed", "error": "recv loop failed"}
                await asyncio.sleep(1)

    async def _handle_gateway_payload(self, payload: dict[str, Any]) -> bool:
        opcode = int(payload.get("op", -1))
        seq = payload.get("s")
        if isinstance(seq, int) and seq > 0:
            self._last_seq = seq

        if opcode == self.WS_HELLO:
            heartbeat_interval = int((payload.get("d") or {}).get("heartbeat_interval", 0) or 0)
            await self._send_identify()
            if heartbeat_interval > 0:
                if self._heartbeat_task is not None:
                    self._heartbeat_task.cancel()
                self._heartbeat_task = asyncio.create_task(
                    self._heartbeat_loop(heartbeat_interval),
                    name="qq-official-heartbeat",
                )
            return True

        if opcode == self.WS_HEARTBEAT_ACK:
            logger.debug("QQ official heartbeat ack received")
            return True

        if opcode == self.WS_RECONNECT:
            logger.warning("QQ official gateway requested reconnect")
            return True

        if opcode == self.WS_INVALID_SESSION:
            logger.error("QQ official invalid session")
            return True

        event_type = str(payload.get("t", "")).strip()
        if event_type == "READY":
            ready = payload.get("d") or {}
            self._session_id = str(ready.get("session_id", "")).strip()
            shard = ready.get("shard") or [0, 1]
            if isinstance(shard, list) and len(shard) == 2:
                self._shard = [int(shard[0]), int(shard[1])]
            self._bot_user = ready.get("user") or {}
            self._sensenova_claw_status = {"status": "connected", "error": None}
            logger.info("QQ official gateway ready: bot=%s session=%s", self._bot_user.get("username", ""), self._session_id)
            return True

        if opcode == self.WS_DISPATCH:
            await self.handle_event(payload)
            return True
        return False

    def _normalize_event(self, payload: dict[str, Any]) -> QQInboundMessage | None:
        event_type = str(payload.get("t", "")).strip()
        data = payload.get("d") or {}
        if event_type not in {
            "DIRECT_MESSAGE_CREATE",
            "C2C_MESSAGE_CREATE",
            "AT_MESSAGE_CREATE",
            "MESSAGE_CREATE",
            "GROUP_AT_MESSAGE_CREATE",
        }:
            return None

        content = str(data.get("content", "")).strip()
        if not content:
            return None

        author = data.get("author") or {}
        if event_type in {"DIRECT_MESSAGE_CREATE", "C2C_MESSAGE_CREATE"}:
            chat_type = "p2p"
            chat_id = str(data.get("channel_id", "")).strip()
            target = f"direct:{chat_id}"
        elif event_type == "GROUP_AT_MESSAGE_CREATE":
            chat_type = "group"
            chat_id = str(data.get("group_openid", "") or data.get("group_id", "")).strip()
            target = f"group:{chat_id}"
        else:
            chat_type = "channel"
            chat_id = str(data.get("channel_id", "")).strip()
            target = f"channel:{chat_id}"

        return QQInboundMessage(
            text=content,
            chat_type=chat_type,
            chat_id=chat_id,
            sender_id=str(author.get("id", "")).strip(),
            sender_name=str(author.get("username", "")).strip(),
            message_id=str(data.get("id", "")).strip(),
            target=target,
            mentioned_bot=self._contains_bot_mention(content),
            reply_to_message_id=str(data.get("id", "")).strip() or None,
            raw_event=payload,
        )

    def _contains_bot_mention(self, content: str) -> bool:
        app_id = str(self._config.official.app_id or "").strip()
        return bool(app_id and f"<@!{app_id}>" in content)

    async def _build_headers(self) -> dict[str, str]:
        if not self._access_token or self._token_expire_at <= time.time():
            await self._refresh_access_token()
        return {"Authorization": f"QQBot {self._access_token}"}

    async def _refresh_access_token(self) -> None:
        app_id = self._config.official.app_id
        client_secret = self._config.official.client_secret
        if not app_id or not client_secret:
            raise RuntimeError("QQ official app_id and client_secret are required")
        async with httpx.AsyncClient(base_url=self._token_base_url(), timeout=20) as client:
            response = await client.post(
                "/app/getAppAccessToken",
                json={"appId": app_id, "clientSecret": client_secret},
            )
            response.raise_for_status()
            data = response.json()
        self._access_token = str(data.get("access_token", "")).strip()
        expires_in = int(data.get("expires_in", 3600) or 3600)
        self._token_expire_at = time.time() + max(expires_in - 60, 60)

    async def _fetch_gateway(self) -> str:
        headers = await self._build_headers()
        async with httpx.AsyncClient(base_url=self._api_base_url(), timeout=20) as client:
            response = await client.get("/gateway/bot", headers=headers)
            response.raise_for_status()
            data = response.json()
        return str(data.get("url", "")).strip()

    async def _send_identify(self) -> None:
        payload = {
            "op": self.WS_IDENTIFY,
            "d": {
                "token": f"QQBot {self._access_token}",
                "intents": self._resolve_intents(),
                "shard": self._shard,
                "properties": {
                    "$os": platform.system().lower() or "linux",
                    "$browser": "sensenova-claw",
                    "$device": "sensenova-claw",
                },
            },
        }
        await self._send_ws_json(payload)

    async def _heartbeat_loop(self, interval_ms: int) -> None:
        interval = max(interval_ms, 1000) / 1000
        while True:
            await asyncio.sleep(interval)
            await self._send_ws_json({"op": self.WS_HEARTBEAT, "d": self._last_seq})

    async def _send_ws_json(self, payload: dict[str, Any]) -> None:
        if self._ws is None:
            raise RuntimeError("QQ official websocket is not connected")
        await self._ws.send(json.dumps(payload))

    def _resolve_intents(self) -> int:
        intent_map = {
            "GUILDS": 1 << 0,
            "GUILD_MESSAGES": 1 << 9,
            "GUILD_MESSAGE_REACTIONS": 1 << 10,
            "DIRECT_MESSAGES": 1 << 12,
            "DIRECT_MESSAGE_CREATE": 1 << 12,
            "ENTER_AIO": 1 << 23,
            "GROUP_MESSAGES": 1 << 25,
            "GROUP_AT_MESSAGE_CREATE": 1 << 25,
            "C2C_MESSAGE_CREATE": 1 << 25,
            "INTERACTION_CREATE": 1 << 26,
            "MESSAGE_AUDIT": 1 << 27,
            "FORUM": 1 << 28,
            "AUDIO": 1 << 29,
            "AT_MESSAGE_CREATE": 1 << 30,
            "PUBLIC_GUILD_MESSAGES": 1 << 30,
        }
        configured = [str(item).strip().upper() for item in (self._config.official.intents or []) if str(item).strip()]
        if not configured:
            configured = ["AT_MESSAGE_CREATE", "DIRECT_MESSAGES", "GROUP_AT_MESSAGE_CREATE", "C2C_MESSAGE_CREATE"]
        resolved = 0
        for item in configured:
            resolved |= intent_map.get(item, 0)
        return resolved or ((1 << 30) | (1 << 12) | (1 << 25))

    def _token_base_url(self) -> str:
        return "https://bots.qq.com"

    def _api_base_url(self) -> str:
        if self._config.official.sandbox:
            return "https://sandbox.api.sgroup.qq.com"
        return "https://api.sgroup.qq.com"
