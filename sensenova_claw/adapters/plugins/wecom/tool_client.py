"""企业微信协议适配客户端。

封装移植后的官方 SDK，并向 Sensenova-Claw 暴露最小文本收发接口。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .config import WecomConfig

logger = logging.getLogger(__name__)


@dataclass
class WecomIncomingMessage:
    """企微入站文本消息。"""

    text: str
    chat_id: str
    chat_type: str
    sender_id: str
    message_id: str


class _SdkLogger:
    """将移植 SDK 的日志转接到 Sensenova-Claw logging。"""

    def debug(self, message: str, *args: Any) -> None:
        logger.debug(message, *args)

    def info(self, message: str, *args: Any) -> None:
        logger.info(message, *args)

    def warn(self, message: str, *args: Any) -> None:
        logger.warning(message, *args)

    def error(self, message: str, *args: Any) -> None:
        logger.error(message, *args)


class WecomToolClient:
    """企业微信客户端包装层。"""

    def __init__(
        self,
        config: WecomConfig,
        on_text_message: Callable[[WecomIncomingMessage], Awaitable[None] | None] | None = None,
        client_factory: Callable[[Any], Any] | None = None,
        options_cls: type | None = None,
    ):
        self._config = config
        self._on_text_message = on_text_message
        self._client_factory = client_factory
        self._options_cls = options_cls
        self._sdk_client: Any | None = None
        self._sensenova_claw_status = {"status": "initialized", "error": None}

    async def start(self) -> None:
        """启动 SDK 客户端并注册文本消息回调。"""
        if self._sdk_client is not None:
            return

        self._sensenova_claw_status = {"status": "connecting", "error": None}

        options_cls = self._options_cls or self._load_options_cls()
        options = options_cls(
            bot_id=self._config.bot_id,
            secret=self._config.secret,
            ws_url=self._config.websocket_url,
            logger=_SdkLogger(),
        )
        factory = self._client_factory or self._load_client_factory()
        self._sdk_client = factory(options)

        @self._sdk_client.on("connected")
        def _on_connected(*_args: Any) -> None:
            self._sensenova_claw_status = {"status": "connected", "error": None}

        @self._sdk_client.on("disconnected")
        def _on_disconnected(reason: Any = None) -> None:
            reason_text = str(reason).strip() if reason is not None else ""
            self._sensenova_claw_status = {
                "status": "failed",
                "error": reason_text or "disconnected",
            }

        @self._sdk_client.on("message.text")
        async def _on_text(frame: dict[str, Any]) -> None:
            incoming = self._parse_text_frame(frame)
            if incoming is None or self._on_text_message is None:
                return
            result = self._on_text_message(incoming)
            if hasattr(result, "__await__"):
                await result

        try:
            await self._sdk_client.connect()
            if self._sensenova_claw_status.get("status") != "failed":
                self._sensenova_claw_status = {"status": "connected", "error": None}
        except Exception as exc:
            self._sensenova_claw_status = {"status": "failed", "error": str(exc)}
            raise

    async def stop(self) -> None:
        """停止 SDK 客户端。"""
        if self._sdk_client is None:
            return
        self._sdk_client.disconnect()
        self._sensenova_claw_status = {"status": "stopped", "error": None}

    async def send_text(self, target: str, text: str) -> dict:
        """通过 SDK 主动发送 Markdown 文本消息。"""
        if self._sdk_client is None:
            return {"success": False, "error": "SDK client not started"}

        response = await self._sdk_client.send_message(
            target,
            {
                "msgtype": "markdown",
                "markdown": {"content": text},
            },
        )
        errcode = response.get("errcode", 0)
        return {
            "success": errcode == 0,
            "message_id": response.get("headers", {}).get("req_id", ""),
            "errcode": errcode,
            "errmsg": response.get("errmsg", ""),
        }

    def _load_client_factory(self) -> Callable[[Any], Any]:
        from .sdk import WSClient

        return WSClient

    def _load_options_cls(self) -> type:
        from .sdk import WSClientOptions

        return WSClientOptions

    def _parse_text_frame(self, frame: dict[str, Any]) -> WecomIncomingMessage | None:
        body = frame.get("body", {})
        text = body.get("text", {}).get("content", "").strip()
        if not text:
            return None

        sender_id = body.get("from", {}).get("userid", "")
        chat_id = body.get("chatid") or sender_id
        raw_chat_type = body.get("chattype", "")
        chat_type = self._normalize_chat_type(raw_chat_type, chat_id, sender_id)
        message_id = (
            frame.get("headers", {}).get("req_id")
            or body.get("msgid")
            or body.get("msg_id")
            or ""
        )

        return WecomIncomingMessage(
            text=text,
            chat_id=chat_id,
            chat_type=chat_type,
            sender_id=sender_id,
            message_id=message_id,
        )

    def _normalize_chat_type(self, raw_chat_type: str, chat_id: str, sender_id: str) -> str:
        chat_type = (raw_chat_type or "").strip().lower()
        if chat_type in {"single", "p2p", "direct", "dm"}:
            return "p2p"
        if chat_type in {"group", "room", "chatroom"}:
            return "group"
        return "p2p" if chat_id == sender_id else "group"
