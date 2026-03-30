"""DingTalk Channel 数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DingtalkConversationType = Literal["p2p", "group"]


@dataclass
class DingtalkInboundMessage:
    """标准化后的 DingTalk 入站消息。"""

    text: str
    conversation_id: str
    conversation_type: DingtalkConversationType
    sender_id: str
    sender_staff_id: str
    sender_nick: str
    message_id: str
    session_webhook: str
    conversation_title: str | None = None
    mentioned_bot: bool = False
    robot_code: str | None = None


@dataclass
class DingtalkSessionMeta:
    """会话回复所需的 DingTalk 元数据。"""

    conversation_id: str
    conversation_type: DingtalkConversationType
    sender_id: str
    sender_staff_id: str
    sender_nick: str
    last_message_id: str
    session_webhook: str
    conversation_title: str | None
    reply_target: str
