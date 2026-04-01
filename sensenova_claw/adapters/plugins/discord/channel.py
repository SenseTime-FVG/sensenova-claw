"""Discord Channel 实现。"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Sequence

from sensenova_claw.adapters.channels.base import Channel
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import (
    AGENT_STEP_COMPLETED,
    CRON_DELIVERY_REQUESTED,
    ERROR_RAISED,
    TOOL_CALL_STARTED,
    USER_INPUT,
    USER_QUESTION_ANSWERED,
    USER_QUESTION_ASKED,
)

from .config import DiscordConfig
from .models import DiscordFeatureHooks, DiscordInboundMessage, DiscordSessionMeta
from .runtime import DiscordRuntime

logger = logging.getLogger(__name__)


@dataclass
class DiscordPendingQuestion:
    question_id: str
    question: str


class DiscordChannel(Channel):
    """Discord Channel。"""

    _session_meta_model = DiscordSessionMeta

    def __init__(
        self,
        config: DiscordConfig,
        plugin_api,
        runtime: DiscordRuntime | None = None,
        feature_hooks: Sequence[DiscordFeatureHooks] | None = None,
    ):
        super().__init__()
        self._config = config
        self._plugin_api = plugin_api
        self._runtime = runtime or DiscordRuntime(config, feature_hooks=feature_hooks)
        self._chat_sessions: dict[str, str] = {}
        self._session_meta: dict[str, DiscordSessionMeta] = {}
        self._pending_questions: dict[str, DiscordPendingQuestion] = {}
        self._sensenova_claw_status: dict[str, str] = {"status": "idle"}

    def get_channel_id(self) -> str:
        return "discord"

    def event_filter(self) -> set[str] | None:
        types = {AGENT_STEP_COMPLETED, ERROR_RAISED, CRON_DELIVERY_REQUESTED, USER_QUESTION_ASKED}
        if self._config.show_tool_progress:
            types.add(TOOL_CALL_STARTED)
        return types

    def on_session_expired(self, session_id: str) -> None:
        """BusRouter GC 清理 session 后，移除内部映射，下次消息自动新建。"""
        self._session_meta.pop(session_id, None)
        self._pending_questions.pop(session_id, None)
        keys_to_remove = [
            key for key, sid in self._chat_sessions.items() if sid == session_id
        ]
        for key in keys_to_remove:
            del self._chat_sessions[key]

    async def start(self) -> None:
        self._runtime.set_message_handler(self.handle_incoming_message)
        try:
            await self._runtime.start()
            self._sensenova_claw_status = {"status": "ready"}
        except Exception as exc:
            self._sensenova_claw_status = {"status": "failed", "error": str(exc).strip() or type(exc).__name__}
            logger.exception("DiscordChannel start failed")
            raise
        logger.info("DiscordChannel started")

    async def stop(self) -> None:
        await self._runtime.stop()
        self._sensenova_claw_status = {"status": "stopped"}
        logger.info("DiscordChannel stopped")

    async def handle_incoming_message(self, message: DiscordInboundMessage) -> None:
        if not message.text.strip():
            return
        if not self._should_respond(message):
            logger.info(
                "Ignore Discord message by policy: channel_type=%s channel_id=%s sender_id=%s",
                message.channel_type,
                message.channel_id,
                message.sender_id,
            )
            return

        session_key = self._build_session_key(message)
        session_id = self._chat_sessions.get(session_key)
        if not session_id:
            session_id = f"discord_{uuid.uuid4().hex[:12]}"
            self._chat_sessions[session_key] = session_id

        self._session_meta[session_id] = DiscordSessionMeta(
            channel_id=message.channel_id,
            channel_type=message.channel_type,
            sender_id=message.sender_id,
            sender_name=message.sender_name,
            last_message_id=message.message_id,
            guild_id=message.guild_id,
            thread_id=message.thread_id,
            parent_channel_id=message.parent_channel_id,
            reply_target_id=self._resolve_reply_target_id(message),
        )

        gateway = self._plugin_api.get_gateway()
        gateway.bind_session(session_id, "discord")
        pending_question = self._pending_questions.pop(session_id, None)
        if pending_question is not None:
            await gateway.publish_from_channel(
                EventEnvelope(
                    type=USER_QUESTION_ANSWERED,
                    session_id=session_id,
                    turn_id=f"turn_{uuid.uuid4().hex[:12]}",
                    source="discord",
                    payload={
                        "question_id": pending_question.question_id,
                        "answer": message.text,
                        "cancelled": False,
                    },
                )
            )
            return

        await gateway.publish_from_channel(
            EventEnvelope(
                type=USER_INPUT,
                session_id=session_id,
                turn_id=f"turn_{uuid.uuid4().hex[:12]}",
                source="discord",
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
        elif event.type == USER_QUESTION_ASKED:
            question = event.payload.get("question", "")
            if question:
                self._pending_questions[event.session_id] = DiscordPendingQuestion(
                    question_id=str(event.payload.get("question_id", "")).strip(),
                    question=question,
                )
                await self._send_reply(event.session_id, question)
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
            logger.warning("No Discord meta for session %s", session_id)
            return
        await self._runtime.send_text(
            meta.reply_target_id,
            text,
            message_reference=meta.last_message_id,
        )

    def _build_session_key(self, message: DiscordInboundMessage) -> str:
        if message.channel_type == "dm":
            return f"dm:{message.sender_id}"
        if message.channel_type == "thread":
            return f"thread:{message.thread_id or message.channel_id}"
        return f"group:{message.channel_id}"

    def _resolve_reply_target_id(self, message: DiscordInboundMessage) -> str:
        if message.channel_type == "thread":
            if self._config.reply_in_thread and message.thread_id:
                return message.thread_id
            if message.parent_channel_id:
                return message.parent_channel_id
        return message.channel_id

    def _should_respond(self, message: DiscordInboundMessage) -> bool:
        if message.channel_type == "dm":
            if self._config.dm_policy == "disabled":
                return False
            if self._config.dm_policy == "allowlist":
                return message.sender_id in set(self._config.allowlist)
            return True

        if self._config.group_policy == "disabled":
            return False
        if self._config.channel_allowlist and message.channel_id not in set(self._config.channel_allowlist):
            return False
        if self._config.group_policy == "allowlist" and message.sender_id not in set(self._config.group_allowlist):
            return False
        if self._config.require_mention and not message.mentioned_bot:
            return False
        return True

