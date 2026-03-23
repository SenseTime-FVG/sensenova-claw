"""Telegram Channel 数据模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TelegramInboundMessage:
    """标准化后的 Telegram 入站文本消息。"""

    text: str
    chat_id: str
    chat_type: str
    sender_id: str
    sender_username: str | None
    message_id: int
    message_thread_id: int | None = None
    mentioned_bot: bool = False


@dataclass
class TelegramSessionMeta:
    """Telegram 会话元数据。"""

    chat_id: str
    chat_type: str
    sender_id: str
    sender_username: str | None
    last_message_id: int
    message_thread_id: int | None = None
