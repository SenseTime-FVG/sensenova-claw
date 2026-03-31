"""QQ Channel 数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

QQChatType = Literal["p2p", "group", "channel"]
QQMode = Literal["official", "onebot"]


@dataclass
class QQInboundMessage:
    """标准化后的 QQ 入站消息。"""

    text: str
    chat_type: QQChatType
    chat_id: str
    sender_id: str
    sender_name: str
    message_id: str
    target: str
    mentioned_bot: bool = False
    reply_to_message_id: str | None = None
    raw_event: dict[str, Any] | None = None


@dataclass
class QQSessionMeta:
    """会话回复所需的 QQ 元数据。"""

    chat_type: QQChatType
    chat_id: str
    sender_id: str
    sender_name: str
    target: str
    reply_to_message_id: str | None
    mode: QQMode

