"""QQ Channel 实现。"""

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

from .config import QQConfig
from .models import QQInboundMessage, QQSessionMeta
from .runtime_base import QQRuntime
from .runtime_official import QQOfficialRuntime
from .runtime_onebot import QQOneBotRuntime

logger = logging.getLogger(__name__)


@dataclass
class QQPendingQuestion:
    question_id: str
    question: str


class QQChannel(Channel):
    """QQ Channel。"""

    _session_meta_model = QQSessionMeta
    _pending_question_model = QQPendingQuestion

    def __init__(
        self,
        config: QQConfig,
        plugin_api,
        runtime: QQRuntime | None = None,
    ):
        super().__init__()
        self._config = config
        self._plugin_api = plugin_api
        self._runtime = runtime or self._create_runtime(config)
        self._sensenova_claw_status = {"status": "initialized", "error": ""}
        self._chat_sessions: dict[str, str] = {}
        self._session_meta: dict[str, QQSessionMeta] = {}
        self._pending_questions: dict[str, QQPendingQuestion] = {}

    def get_channel_id(self) -> str:
        return "qq"

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
            logger.exception("QQChannel start failed")
            raise
        self._sensenova_claw_status = {"status": "connected", "error": ""}
        logger.info("QQChannel started in mode=%s", self._config.mode)

    async def stop(self) -> None:
        await self._runtime.stop()
        self._sensenova_claw_status = {"status": "stopped", "error": ""}
        logger.info("QQChannel stopped")

    async def handle_incoming_message(self, message: QQInboundMessage) -> None:
        if not message.text.strip():
            return
        if not self._should_respond(message):
            logger.info(
                "Ignore QQ message by policy: mode=%s chat_type=%s chat_id=%s sender_id=%s",
                self._config.mode,
                message.chat_type,
                message.chat_id,
                message.sender_id,
            )
            return

        session_key = self._build_session_key(message)
        session_id = self._chat_sessions.get(session_key)
        if not session_id:
            session_id = f"qq_{uuid.uuid4().hex[:12]}"
            self._chat_sessions[session_key] = session_id

        self._session_meta[session_id] = QQSessionMeta(
            chat_type=message.chat_type,
            chat_id=message.chat_id,
            sender_id=message.sender_id,
            sender_name=message.sender_name,
            target=message.target,
            reply_to_message_id=message.message_id if self._config.reply_to_message else None,
            mode=self._config.mode,
        )

        gateway = self._plugin_api.get_gateway()
        gateway.bind_session(session_id, "qq")
        pending_question = self._pending_questions.pop(session_id, None)
        if pending_question is not None:
            await gateway.publish_from_channel(
                EventEnvelope(
                    type=USER_QUESTION_ANSWERED,
                    session_id=session_id,
                    turn_id=f"turn_{uuid.uuid4().hex[:12]}",
                    source="qq",
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
                source="qq",
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
                self._pending_questions[event.session_id] = QQPendingQuestion(
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
            logger.warning("No QQ meta for session %s", session_id)
            return
        await self._runtime.send_text(
            meta.target,
            text,
            reply_to_message_id=meta.reply_to_message_id,
        )

    def _build_session_key(self, message: QQInboundMessage) -> str:
        if message.chat_type == "p2p":
            return f"dm:{message.sender_id}"
        if message.chat_type == "channel":
            return f"channel:{message.chat_id}"
        return f"group:{message.chat_id}"

    def _should_respond(self, message: QQInboundMessage) -> bool:
        if message.chat_type == "p2p":
            if self._config.dm_policy == "disabled":
                return False
            if self._config.dm_policy == "allowlist":
                return message.sender_id in set(self._config.allowlist)
            return True

        if self._config.group_policy == "disabled":
            return False
        if self._config.group_policy == "allowlist" and message.sender_id not in set(self._config.group_allowlist):
            return False
        if self._config.require_mention and not message.mentioned_bot:
            return False
        return True

    def _create_runtime(self, config: QQConfig) -> QQRuntime:
        if config.mode == "official":
            return QQOfficialRuntime(config)
        return QQOneBotRuntime(config)

