"""基于 python-telegram-bot 的 Telegram runtime。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
import inspect

from fastapi import FastAPI, Header, HTTPException, Request
from telegram import Bot, Message, Update
from telegram.error import Conflict
from telegram.request import HTTPXRequest
import uvicorn

from sensenova_claw.platform.security.ssl import CERTIFI_SSL_CONTEXT

from .config import TelegramConfig
from .models import TelegramInboundMessage

logger = logging.getLogger(__name__)

MessageHandler = Callable[[TelegramInboundMessage], Awaitable[None]]
_SSL_CONTEXT = CERTIFI_SSL_CONTEXT


class TelegramRuntime:
    """Telegram Bot API runtime。"""

    def __init__(self, config: TelegramConfig):
        self._config = config
        request = HTTPXRequest(httpx_kwargs={"verify": _SSL_CONTEXT})
        get_updates_request = HTTPXRequest(httpx_kwargs={"verify": _SSL_CONTEXT})
        self._bot = Bot(token=config.bot_token, request=request, get_updates_request=get_updates_request)
        self._message_handler: MessageHandler | None = None
        self._bot_username: str | None = None
        self._poll_task: asyncio.Task | None = None
        self._server: uvicorn.Server | None = None
        self._server_task: asyncio.Task | None = None
        self._sensenova_claw_status = {"status": "initialized", "error": None}

    def set_message_handler(self, handler: MessageHandler) -> None:
        self._message_handler = handler

    def set_bot_username(self, username: str | None) -> None:
        self._bot_username = username.lstrip("@") if username else None

    async def start(self) -> None:
        self._sensenova_claw_status = {"status": "connecting", "error": None}
        try:
            me = await self._bot.get_me()
            self.set_bot_username(me.username)

            if self._config.mode == "webhook":
                await self._start_webhook()
                self._sensenova_claw_status = {"status": "connected", "error": None}
                logger.info("TelegramRuntime started in webhook mode")
                return

            self._poll_task = asyncio.create_task(self._poll_loop(), name="telegram-polling")
            self._sensenova_claw_status = {"status": "connected", "error": None}
            logger.info("TelegramRuntime started in polling mode")
        except Exception as exc:
            self._sensenova_claw_status = {"status": "failed", "error": str(exc)}
            raise

    async def stop(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

        if self._server:
            self._server.should_exit = True
        if self._server_task:
            await self._server_task
            self._server_task = None
            self._server = None

        if self._config.mode == "webhook" and self._config.webhook_url:
            try:
                await self._bot.delete_webhook()
            except Exception:
                logger.exception("Failed to delete Telegram webhook")
        self._sensenova_claw_status = {"status": "stopped", "error": None}

    async def handle_update(self, update: Update) -> None:
        message = update.effective_message
        if not message:
            return
        inbound = self._convert_message(message)
        if not inbound:
            return
        if self._message_handler:
            result = self._message_handler(inbound)
            if inspect.isawaitable(result):
                await result

    async def send_text(
        self,
        chat_id: str,
        text: str,
        *,
        reply_to_message_id: int | None = None,
        message_thread_id: int | None = None,
    ) -> dict:
        response = await self._bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_to_message_id=reply_to_message_id,
            message_thread_id=message_thread_id,
        )
        return {"success": True, "message_id": str(response.message_id)}

    async def _poll_loop(self) -> None:
        offset: int | None = None
        while True:
            try:
                updates = await self._bot.get_updates(
                    offset=offset,
                    timeout=self._config.polling_timeout_seconds,
                    allowed_updates=Update.ALL_TYPES,
                )
                self._sensenova_claw_status = {"status": "connected", "error": None}
                for update in updates:
                    offset = update.update_id + 1
                    await self.handle_update(update)
            except asyncio.CancelledError:
                raise
            except Conflict as exc:
                self._sensenova_claw_status = {"status": "failed", "error": str(exc).strip() or type(exc).__name__}
                logger.error(
                    "Telegram polling stopped due to getUpdates conflict: %s",
                    self._sensenova_claw_status["error"],
                )
                return
            except Exception as exc:
                self._sensenova_claw_status = {"status": "failed", "error": str(exc)}
                logger.exception("Telegram polling loop failed")
                await asyncio.sleep(1)

    async def _start_webhook(self) -> None:
        app = FastAPI()

        @app.post(self._config.webhook_path)
        async def telegram_webhook(
            request: Request,
            x_telegram_bot_api_secret_token: str | None = Header(default=None),
        ) -> dict:
            if self._config.webhook_secret:
                if x_telegram_bot_api_secret_token != self._config.webhook_secret:
                    raise HTTPException(status_code=403, detail="invalid telegram secret")

            payload = await request.json()
            update = Update.de_json(payload, self._bot)
            await self.handle_update(update)
            return {"ok": True}

        server_config = uvicorn.Config(
            app=app,
            host=self._config.webhook_host,
            port=self._config.webhook_port,
            log_level="info",
        )
        self._server = uvicorn.Server(server_config)
        self._server_task = asyncio.create_task(self._server.serve(), name="telegram-webhook")

        if self._config.webhook_url:
            await self._bot.set_webhook(
                url=self._config.webhook_url,
                secret_token=self._config.webhook_secret or None,
            )

    def _convert_message(self, message: Message) -> TelegramInboundMessage | None:
        text = (message.text or message.caption or "").strip()
        if not text:
            return None

        chat_type = "p2p" if message.chat.type == "private" else "group"
        sender = message.from_user
        sender_id = str(sender.id) if sender else ""
        sender_username = sender.username if sender else None

        return TelegramInboundMessage(
            text=text,
            chat_id=str(message.chat.id),
            chat_type=chat_type,
            sender_id=sender_id,
            sender_username=sender_username,
            message_id=message.message_id,
            message_thread_id=getattr(message, "message_thread_id", None),
            mentioned_bot=self._is_bot_mentioned(message, text),
        )

    def _is_bot_mentioned(self, message: Message, text: str) -> bool:
        if not self._bot_username:
            return False
        expected = f"@{self._bot_username}".lower()

        for entity in message.entities or []:
            if entity.type == "mention":
                mention = text[entity.offset : entity.offset + entity.length]
                if mention.lower() == expected:
                    return True
        return False
