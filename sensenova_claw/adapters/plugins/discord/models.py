"""Discord Channel 数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

DiscordChannelType = Literal["dm", "group", "thread"]


@dataclass
class DiscordInboundMessage:
    """标准化后的 Discord 入站消息。"""

    text: str
    channel_id: str
    channel_type: DiscordChannelType
    sender_id: str
    sender_name: str
    message_id: str
    guild_id: str | None = None
    thread_id: str | None = None
    parent_channel_id: str | None = None
    mentioned_bot: bool = False


@dataclass
class DiscordSessionMeta:
    """会话回复所需的 Discord 元数据。"""

    channel_id: str
    channel_type: DiscordChannelType
    sender_id: str
    sender_name: str
    last_message_id: str
    guild_id: str | None
    thread_id: str | None
    parent_channel_id: str | None
    reply_target_id: str


class DiscordFeatureHooks(Protocol):
    """为后续 slash command、线程绑定等能力预留扩展接口。"""

    async def on_ready(self, runtime: object) -> None:
        """Discord runtime 就绪后回调。"""

    async def on_message(self, message: DiscordInboundMessage) -> None:
        """标准化入站消息后回调。"""

