"""DingTalk Channel 实现。"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

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

from .config import DingtalkConfig
from .models import DingtalkInboundMessage, DingtalkSessionMeta
from .runtime import DingtalkRuntime

logger = logging.getLogger(__name__)


@dataclass
class DingtalkPendingQuestion:
    question_id: str
    question: str


class DingtalkChannel(Channel):
    """DingTalk Channel。"""

    _session_meta_model = DingtalkSessionMeta
    _pending_question_model = DingtalkPendingQuestion

    def __init__(
        self,
        config: DingtalkConfig,
        plugin_api,
        runtime: DingtalkRuntime | None = None,
    ):
        super().__init__()
        self._config = config
        self._plugin_api = plugin_api
        self._runtime = runtime or DingtalkRuntime(config)
        self._sensenova_claw_status = {"status": "initialized", "error": ""}
        self._chat_sessions: dict[str, str] = {}
        self._session_meta: dict[str, DingtalkSessionMeta] = {}
        self._pending_questions: dict[str, DingtalkPendingQuestion] = {}

    def get_channel_id(self) -> str:
        return "dingtalk"

    def event_filter(self) -> set[str] | None:
        types = {AGENT_STEP_COMPLETED, ERROR_RAISED, CRON_DELIVERY_REQUESTED, USER_QUESTION_ASKED}
        if self._config.show_tool_progress:
            types.add(TOOL_CALL_STARTED)
        return types

    async def start(self) -> None:
        self._runtime.set_message_handler(self.handle_incoming_message)
        self._sensenova_claw_status = {"status": "connecting", "error": ""}
        try:
            await self._runtime.start()
        except Exception as exc:
            self._sensenova_claw_status = {"status": "failed", "error": str(exc).strip() or type(exc).__name__}
            logger.exception("DingTalkChannel start failed")
            raise
        self._sensenova_claw_status = {"status": "connected", "error": ""}
        logger.info("DingTalkChannel started")

    async def stop(self) -> None:
        await self._runtime.stop()
        self._sensenova_claw_status = {"status": "stopped", "error": ""}
        logger.info("DingTalkChannel stopped")

    async def handle_incoming_message(self, message: DingtalkInboundMessage) -> None:
        if not message.text.strip():
            return
        if not self._should_respond(message):
            logger.info(
                "Ignore DingTalk message by policy: conversation_type=%s conversation_id=%s sender_staff_id=%s",
                message.conversation_type,
                message.conversation_id,
                message.sender_staff_id,
            )
            return

        session_key = self._build_session_key(message)
        session_id = self._chat_sessions.get(session_key)
        if not session_id:
            session_id = f"dingtalk_{uuid.uuid4().hex[:12]}"
            self._chat_sessions[session_key] = session_id

        reply_target = (
            f"user:{message.sender_staff_id}"
            if self._config.reply_to_sender and message.sender_staff_id
            else f"conversation:{message.conversation_id}"
        )
        self._session_meta[session_id] = DingtalkSessionMeta(
            conversation_id=message.conversation_id,
            conversation_type=message.conversation_type,
            sender_id=message.sender_id,
            sender_staff_id=message.sender_staff_id,
            sender_nick=message.sender_nick,
            last_message_id=message.message_id,
            session_webhook=message.session_webhook,
            conversation_title=message.conversation_title,
            reply_target=reply_target,
        )

        gateway = self._plugin_api.get_gateway()
        gateway.bind_session(session_id, "dingtalk")

        pending_question = self._pending_questions.pop(session_id, None)
        if pending_question is not None:
            await gateway.publish_from_channel(
                EventEnvelope(
                    type=USER_QUESTION_ANSWERED,
                    session_id=session_id,
                    turn_id=f"turn_{uuid.uuid4().hex[:12]}",
                    source="dingtalk",
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
                source="dingtalk",
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
                self._pending_questions[event.session_id] = DingtalkPendingQuestion(
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
            logger.warning("No DingTalk meta for session %s", session_id)
            return
        target = f"webhook:{meta.session_webhook}" if meta.session_webhook else meta.reply_target
        await self._runtime.send_text(target, text)

    def _build_session_key(self, message: DingtalkInboundMessage) -> str:
        if message.conversation_type == "p2p":
            return f"dm:{message.sender_staff_id or message.sender_id}"
        return f"group:{message.conversation_id}"

    def _should_respond(self, message: DingtalkInboundMessage) -> bool:
        if message.conversation_type == "p2p":
            if self._config.dm_policy == "disabled":
                return False
            if self._config.dm_policy == "allowlist":
                return message.sender_staff_id in set(self._config.allowlist)
            return True

        if self._config.group_policy == "disabled":
            return False
        if self._config.group_policy == "allowlist" and message.sender_staff_id not in set(self._config.group_allowlist):
            return False
        if self._config.require_mention and not message.mentioned_bot:
            return False
        return True
