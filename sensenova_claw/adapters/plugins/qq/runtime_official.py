"""QQ 官方开放平台 runtime。"""

from __future__ import annotations

import asyncio
import json
import logging
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

    def __init__(self, config: QQConfig):
        self._config = config
        self._message_handler: QQMessageHandler | None = None
        self._gateway_task: asyncio.Task | None = None
        self._ws = None
        self._access_token: str = ""
        self._token_expire_at: float = 0
        self._sensenova_claw_status = {"status": "initialized", "error": None}

    def set_message_handler(self, handler: QQMessageHandler) -> None:
        self._message_handler = handler

    async def start(self) -> None:
        await self._refresh_access_token()
        gateway = await self._fetch_gateway()
        self._ws = await websockets.connect(gateway)
        self._gateway_task = asyncio.create_task(self._recv_loop(), name="qq-official-recv")
        self._sensenova_claw_status = {"status": "connected", "error": None}

    async def stop(self) -> None:
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
                await self.handle_event(payload)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("QQ official recv loop failed")
                self._sensenova_claw_status = {"status": "failed", "error": "recv loop failed"}
                await asyncio.sleep(1)

    def _normalize_event(self, payload: dict[str, Any]) -> QQInboundMessage | None:
        event_type = str(payload.get("t", "")).strip()
        data = payload.get("d") or {}
        if event_type not in {"DIRECT_MESSAGE_CREATE", "AT_MESSAGE_CREATE", "MESSAGE_CREATE", "GROUP_AT_MESSAGE_CREATE"}:
            return None

        content = str(data.get("content", "")).strip()
        if not content:
            return None

        author = data.get("author") or {}
        if event_type == "DIRECT_MESSAGE_CREATE":
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
        async with httpx.AsyncClient(base_url=self._api_base_url(), timeout=20) as client:
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
            response = await client.get("/gateway", headers=headers)
            response.raise_for_status()
            data = response.json()
        return str(data.get("url", "")).strip()

    def _api_base_url(self) -> str:
        if self._config.official.sandbox:
            return "https://sandbox.api.sgroup.qq.com"
        return "https://api.sgroup.qq.com"

