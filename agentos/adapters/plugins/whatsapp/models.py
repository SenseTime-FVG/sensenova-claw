"""WhatsApp Channel 数据模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WhatsAppInboundMessage:
    """WhatsApp 入站消息。"""

    text: str
    chat_jid: str
    chat_type: str
    sender_jid: str
    message_id: str
    push_name: str | None = None


@dataclass
class WhatsAppSessionMeta:
    """WhatsApp 会话元数据。"""

    chat_jid: str
    chat_type: str
    sender_jid: str
    last_message_id: str


@dataclass
class WhatsAppRuntimeState:
    """WhatsApp runtime 状态快照。"""

    state: str = "idle"
    connected: bool = False
    jid: str | None = None
    phone: str | None = None
    last_error: str | None = None
    last_qr: str | None = None
    last_qr_data_url: str | None = None
    last_status_code: int | None = None
    last_event: str | None = None
    last_event_at: float | None = None
    debug_message: str | None = None
