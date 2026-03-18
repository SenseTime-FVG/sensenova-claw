"""Telegram Channel 实现。"""

from __future__ import annotations

import logging
import uuid

from agentos.adapters.channels.base import Channel
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import AGENT_STEP_COMPLETED, CRON_DELIVERY_REQUESTED, ERROR_RAISED, TOOL_CALL_STARTED, USER_INPUT

from .config import TelegramConfig
from .models import TelegramInboundMessage, TelegramSessionMeta
from .runtime import TelegramRuntime

logger = logging.getLogger(__name__)


class TelegramChannel(Channel):
    """Telegram Channel。"""

    _session_meta_model = TelegramSessionMeta

    def __init__(
        self,
        config: TelegramConfig,
        plugin_api,
        runtime: TelegramRuntime | None = None,
    ):
        super().__init__()
        self._config = config
        self._plugin_api = plugin_api
        self._runtime = runtime or TelegramRuntime(config)
        self._chat_sessions: dict[str, str] = {}
        self._session_meta: dict[str, TelegramSessionMeta] = {}

    def get_channel_id(self) -> str:
        return "telegram"

    def event_filter(self) -> set[str] | None:
        types = {AGENT_STEP_COMPLETED, ERROR_RAISED, CRON_DELIVERY_REQUESTED}
        if self._config.show_tool_progress:
            types.add(TOOL_CALL_STARTED)
        return types

    async def start(self) -> None:
        self._runtime.set_message_handler(self.handle_incoming_message)
        await self._runtime.start()
        logger.info("TelegramChannel started")

    async def stop(self) -> None:
        await self._runtime.stop()
        logger.info("TelegramChannel stopped")

    async def handle_incoming_message(self, message: TelegramInboundMessage) -> None:
        if not message.text.strip():
            return
        if not self._should_respond(message):
            logger.info(
                "Ignore Telegram message by policy: chat_type=%s chat_id=%s sender_id=%s",
                message.chat_type,
                message.chat_id,
                message.sender_id,
            )
            return

        session_key = self._build_session_key(message)
        session_id = self._chat_sessions.get(session_key)
        if not session_id:
            session_id = f"telegram_{uuid.uuid4().hex[:12]}"
            self._chat_sessions[session_key] = session_id

        self._session_meta[session_id] = TelegramSessionMeta(
            chat_id=message.chat_id,
            chat_type=message.chat_type,
            sender_id=message.sender_id,
            sender_username=message.sender_username,
            last_message_id=message.message_id,
            message_thread_id=message.message_thread_id,
        )

        gateway = self._plugin_api.get_gateway()
        gateway.bind_session(session_id, "telegram")
        await gateway.publish_from_channel(
            EventEnvelope(
                type=USER_INPUT,
                session_id=session_id,
                turn_id=f"turn_{uuid.uuid4().hex[:12]}",
                source="telegram",
                payload={
                    "content": message.text,
                    "attachments": [],
                    "context_files": [],
                },
            )
        )

    async def send_event(self, event: EventEnvelope) -> None:
        if event.type == AGENT_STEP_COMPLETED:
            text = event.payload.get("result", {}).get("content", "") or event.payload.get("final_response", "")
            if text:
                await self._send_reply(event.session_id, text)
        elif event.type == ERROR_RAISED:
            error_message = event.payload.get("error_message", "处理失败")
            await self._send_reply(event.session_id, f"错误: {error_message}")
        elif event.type == TOOL_CALL_STARTED and self._config.show_tool_progress:
            tool_name = event.payload.get("tool_name", "")
            if tool_name:
                await self._send_reply(event.session_id, f"正在执行 {tool_name}...")
        elif event.type == CRON_DELIVERY_REQUESTED:
            text = event.payload.get("text", "")
            target = event.payload.get("to")
            if text and target:
                await self.send_outbound(target=target, text=text)

    async def send_outbound(self, target: str, text: str, msg_type: str = "text") -> dict:
        del msg_type
        return await self._runtime.send_text(str(target), text)

    async def _send_reply(self, session_id: str, text: str) -> None:
        meta = self._session_meta.get(session_id)
        if not meta:
            logger.warning("No Telegram meta for session %s", session_id)
            return
        await self._runtime.send_text(
            meta.chat_id,
            text,
            reply_to_message_id=meta.last_message_id if self._config.reply_to_message else None,
            message_thread_id=meta.message_thread_id,
        )

    def _build_session_key(self, message: TelegramInboundMessage) -> str:
        if message.chat_type == "p2p":
            return f"dm:{message.sender_id}"
        if message.message_thread_id is not None:
            return f"group:{message.chat_id}:topic:{message.message_thread_id}"
        return f"group:{message.chat_id}"

    def _should_respond(self, message: TelegramInboundMessage) -> bool:
        if message.chat_type == "p2p":
            if self._config.dm_policy == "disabled":
                return False
            if self._config.dm_policy == "allowlist":
                return message.sender_id in set(self._config.allowlist)
            return True

        if self._config.group_policy == "disabled":
            return False
        if self._config.group_chat_allowlist and message.chat_id not in set(self._config.group_chat_allowlist):
            return False
        if self._config.group_policy == "allowlist" and message.sender_id not in set(self._config.group_allowlist):
            return False
        if self._config.require_mention and not message.mentioned_bot:
            return False
        return True
