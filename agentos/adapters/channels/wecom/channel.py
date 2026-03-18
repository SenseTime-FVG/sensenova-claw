"""企业微信 Channel 实现。"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from agentos.adapters.channels.base import Channel
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import AGENT_STEP_COMPLETED, ERROR_RAISED, TOOL_CALL_STARTED, USER_INPUT

from .config import WecomConfig
from .tool_client import WecomToolClient

logger = logging.getLogger(__name__)


@dataclass
class WecomSessionMeta:
    """企业微信会话元数据。"""

    chat_id: str
    chat_type: str
    sender_id: str
    last_message_id: str


class WecomChannel(Channel):
    """企业微信 Channel 第一版骨架。"""

    def __init__(self, config: WecomConfig, plugin_api, client: WecomToolClient | None = None):
        self._config = config
        self._plugin_api = plugin_api
        self._client = client or WecomToolClient(
            config=config,
            on_text_message=self._on_client_text_message,
        )
        self._chat_sessions: dict[str, str] = {}
        self._session_meta: dict[str, WecomSessionMeta] = {}

    def get_channel_id(self) -> str:
        return "wecom"

    async def start(self) -> None:
        await self._client.start()
        logger.info("WecomChannel started")

    async def stop(self) -> None:
        await self._client.stop()
        logger.info("WecomChannel stopped")

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

    async def _on_client_text_message(self, message) -> None:
        await self.handle_incoming_text(
            text=message.text,
            chat_id=message.chat_id,
            chat_type=message.chat_type,
            sender_id=message.sender_id,
            message_id=message.message_id,
        )

    async def handle_incoming_text(
        self,
        *,
        text: str,
        chat_id: str,
        chat_type: str,
        sender_id: str,
        message_id: str,
    ) -> None:
        """处理企微入站文本消息。"""
        if not self._should_respond(chat_type, sender_id, chat_id):
            logger.info(
                "Ignore wecom message: chat_type=%s chat_id=%s sender_id=%s",
                chat_type,
                chat_id,
                sender_id,
            )
            return

        session_key = self._build_session_key(chat_type, chat_id, sender_id)
        session_id = self._chat_sessions.get(session_key)
        if not session_id:
            session_id = f"wecom_{uuid.uuid4().hex[:12]}"
            self._chat_sessions[session_key] = session_id

        self._session_meta[session_id] = WecomSessionMeta(
            chat_id=chat_id,
            chat_type=chat_type,
            sender_id=sender_id,
            last_message_id=message_id,
        )

        gateway = self._plugin_api.get_gateway()
        gateway.bind_session(session_id, "wecom")
        await gateway.publish_from_channel(
            EventEnvelope(
                type=USER_INPUT,
                session_id=session_id,
                turn_id=f"turn_{uuid.uuid4().hex[:12]}",
                source="wecom",
                payload={
                    "content": text,
                    "attachments": [],
                    "context_files": [],
                },
            )
        )

    def _build_session_key(self, chat_type: str, chat_id: str, sender_id: str) -> str:
        if chat_type == "p2p":
            return f"dm:{sender_id}"
        return f"group:{chat_id}"

    def _should_respond(self, chat_type: str, sender_id: str, chat_id: str) -> bool:
        if chat_type == "p2p":
            if self._config.dm_policy == "disabled":
                return False
            if self._config.dm_policy == "allowlist":
                return sender_id in self._config.allowlist
            return True

        if chat_type == "group":
            if self._config.group_policy == "disabled":
                return False
            if self._config.group_policy == "allowlist":
                return chat_id in self._config.group_allowlist
            return True

        return False

    async def _send_reply(self, session_id: str, text: str) -> None:
        meta = self._session_meta.get(session_id)
        if not meta:
            logger.warning("No wecom meta for session %s", session_id)
            return
        await self._client.send_text(meta.chat_id, text)

    async def send_outbound(self, target: str, text: str, msg_type: str = "text") -> dict:
        return await self._client.send_text(target, text)
