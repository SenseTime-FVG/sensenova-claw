"""WhatsApp Channel 实现。"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass

from agentos.adapters.channels.base import Channel
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import (
    AGENT_STEP_COMPLETED,
    CRON_DELIVERY_REQUESTED,
    ERROR_RAISED,
    TOOL_CALL_STARTED,
    USER_INPUT,
    USER_QUESTION_ANSWERED,
    USER_QUESTION_ASKED,
)

from .bridge_client import LocalBridgeStub, SidecarBridgeClient, WhatsAppBridgeClient
from .config import WhatsAppConfig
from .models import WhatsAppInboundMessage, WhatsAppRuntimeState, WhatsAppSessionMeta

logger = logging.getLogger(__name__)


@dataclass
class WhatsAppPendingQuestion:
    question_id: str
    question: str


class WhatsAppChannel(Channel):
    """WhatsApp Channel 核心实现。"""

    _session_meta_model = WhatsAppSessionMeta

    def __init__(
        self,
        config: WhatsAppConfig,
        plugin_api,
        bridge: WhatsAppBridgeClient | None = None,
    ):
        super().__init__()
        self._config = config
        self._plugin_api = plugin_api
        self._bridge = bridge or self._build_default_bridge(config)
        self._chat_sessions: dict[str, str] = {}
        self._session_meta: dict[str, WhatsAppSessionMeta] = {}
        self._pending_questions: dict[str, WhatsAppPendingQuestion] = {}
        self._runtime_state = WhatsAppRuntimeState()

    def _build_default_bridge(self, config: WhatsAppConfig) -> WhatsAppBridgeClient:
        if not config.bridge.entry:
            return LocalBridgeStub(config.auth_dir)
        return SidecarBridgeClient(
            command=config.bridge.command,
            entry=config.bridge.entry,
            auth_dir=config.auth_dir,
            typing_indicator=config.typing_indicator,
            startup_timeout_seconds=config.bridge.startup_timeout_seconds,
            send_timeout_seconds=config.bridge.send_timeout_seconds,
        )

    def get_channel_id(self) -> str:
        return "whatsapp"

    def event_filter(self) -> set[str] | None:
        types = {AGENT_STEP_COMPLETED, ERROR_RAISED, CRON_DELIVERY_REQUESTED, USER_QUESTION_ASKED}
        if self._config.show_tool_progress:
            types.add(TOOL_CALL_STARTED)
        return types

    async def start(self) -> None:
        self._bridge.set_message_handler(self.handle_incoming_message)
        if hasattr(self._bridge, "set_event_handler"):
            self._bridge.set_event_handler(self._handle_bridge_event)
        try:
            await self._bridge.start()
        except Exception as exc:
            self._runtime_state.state = "error"
            self._runtime_state.connected = False
            self._runtime_state.last_error = str(exc).strip() or type(exc).__name__
            self._runtime_state.last_event = "start_failed"
            self._runtime_state.last_event_at = time.time()
            self._runtime_state.debug_message = "bridge start failed"
            logger.exception("WhatsAppChannel start failed")
            return
        logger.info("WhatsAppChannel started")

    async def stop(self) -> None:
        await self._bridge.stop()
        logger.info("WhatsAppChannel stopped")

    async def handle_incoming_message(self, message: WhatsAppInboundMessage) -> None:
        """处理 bridge 转发的入站文本消息。"""
        if not message.text.strip():
            logger.debug("Ignore empty WhatsApp message: %s", message.message_id)
            return

        if not self._should_respond(message.chat_type, message.sender_jid, message.chat_jid):
            logger.info(
                "Ignore WhatsApp message by policy: chat_type=%s chat_jid=%s sender_jid=%s",
                message.chat_type,
                message.chat_jid,
                message.sender_jid,
            )
            return

        session_key = self._build_session_key(message.chat_type, message.chat_jid, message.sender_jid)
        session_id = self._chat_sessions.get(session_key)
        if not session_id:
            session_id = f"whatsapp_{uuid.uuid4().hex[:12]}"
            self._chat_sessions[session_key] = session_id

        self._session_meta[session_id] = WhatsAppSessionMeta(
            chat_jid=message.chat_jid,
            chat_type=message.chat_type,
            sender_jid=message.sender_jid,
            last_message_id=message.message_id,
        )

        logger.debug(
            "WhatsApp inbound mapped to session: session_id=%s chat_jid=%s sender_jid=%s text=%s",
            session_id,
            message.chat_jid,
            message.sender_jid,
            message.text[:200],
        )

        gateway = self._plugin_api.get_gateway()
        gateway.bind_session(session_id, "whatsapp")
        pending_question = self._pending_questions.pop(session_id, None)
        if pending_question is not None:
            await gateway.publish_from_channel(
                EventEnvelope(
                    type=USER_QUESTION_ANSWERED,
                    session_id=session_id,
                    turn_id=f"turn_{uuid.uuid4().hex[:12]}",
                    source="whatsapp",
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
                source="whatsapp",
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
                self._pending_questions[event.session_id] = WhatsAppPendingQuestion(
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

    async def _send_reply(self, session_id: str, text: str) -> None:
        meta = self._session_meta.get(session_id)
        if not meta:
            logger.warning("No WhatsApp meta for session %s", session_id)
            return
        result = await self._bridge.send_text(meta.chat_jid, text)
        logger.debug("WhatsApp send reply result: session_id=%s result=%s", session_id, result)

    async def send_outbound(self, target: str, text: str, msg_type: str = "text") -> dict:
        del msg_type
        result = await self._bridge.send_text(target, text)
        logger.debug("WhatsApp outbound result: target=%s result=%s", target, result)
        return result

    async def _handle_bridge_event(self, event: dict) -> None:
        event_type = event.get("type", "")
        payload = event.get("payload", {})

        if event_type == "status":
            self._runtime_state = WhatsAppRuntimeState(
                state=payload.get("state", self._runtime_state.state),
                connected=bool(payload.get("connected", self._runtime_state.connected)),
                jid=payload.get("jid", self._runtime_state.jid),
                phone=payload.get("phone", self._runtime_state.phone),
                last_error=payload.get("lastError", self._runtime_state.last_error),
                last_qr=payload.get("lastQr", self._runtime_state.last_qr),
                last_qr_data_url=payload.get("lastQrDataUrl", self._runtime_state.last_qr_data_url),
                last_status_code=payload.get("lastStatusCode", self._runtime_state.last_status_code),
                last_event=payload.get("lastEvent", self._runtime_state.last_event),
                last_event_at=payload.get("lastEventAt", self._runtime_state.last_event_at),
                debug_message=payload.get("debugMessage", self._runtime_state.debug_message),
            )
            logger.info(
                "WhatsApp runtime status: state=%s connected=%s phone=%s",
                self._runtime_state.state,
                self._runtime_state.connected,
                self._runtime_state.phone,
            )
        elif event_type == "qr":
            self._runtime_state.last_qr = payload.get("text")
            self._runtime_state.last_qr_data_url = payload.get("data_url")
            self._runtime_state.last_event = "qr"
            self._runtime_state.last_event_at = time.time()
            self._runtime_state.debug_message = payload.get("debug_message", self._runtime_state.debug_message)
            logger.info("WhatsApp QR updated, waiting for scan")
        elif event_type == "error":
            self._runtime_state.last_error = payload.get("message")
            self._runtime_state.last_status_code = payload.get("status_code", self._runtime_state.last_status_code)
            self._runtime_state.last_event = "error"
            self._runtime_state.last_event_at = time.time()
            self._runtime_state.debug_message = payload.get("debug_message", self._runtime_state.debug_message)
            logger.error("WhatsApp runtime error: %s", self._runtime_state.last_error)
        elif event_type == "debug":
            self._runtime_state.last_event = "debug"
            self._runtime_state.last_event_at = time.time()
            self._runtime_state.debug_message = payload.get("message")
            logger.debug("WhatsApp runtime debug: %s", self._runtime_state.debug_message)

    def _build_session_key(self, chat_type: str, chat_jid: str, sender_jid: str) -> str:
        if chat_type == "p2p":
            return f"dm:{self._normalize_sender(sender_jid)}"
        return f"group:{chat_jid}"

    def _should_respond(self, chat_type: str, sender_jid: str, chat_jid: str) -> bool:
        normalized_sender = self._normalize_sender(sender_jid)

        if chat_type == "p2p":
            if self._config.dm_policy == "disabled":
                return False
            if self._config.dm_policy == "allowlist":
                return normalized_sender in {self._normalize_allowlist_entry(item) for item in self._config.allowlist}
            return True

        if chat_type == "group":
            if self._config.group_policy == "disabled":
                return False
            if self._config.group_policy == "allowlist":
                return chat_jid in set(self._config.group_allowlist)
            return True

        return False

    def _normalize_sender(self, sender_jid: str) -> str:
        digits = sender_jid.split("@", 1)[0].split(":", 1)[0]
        return f"+{digits}" if digits and not digits.startswith("+") else digits

    def _normalize_allowlist_entry(self, value: str) -> str:
        stripped = value.strip()
        if "@" in stripped:
            return self._normalize_sender(stripped)
        return stripped if stripped.startswith("+") else f"+{stripped}"
