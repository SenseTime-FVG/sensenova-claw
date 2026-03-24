from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from sensenova_claw.kernel.events.envelope import EventEnvelope

if TYPE_CHECKING:
    from sensenova_claw.interfaces.ws.gateway import Gateway


class Channel(ABC):
    """Channel 抽象基类

    Channel 负责协议适配和各自的认证，Gateway 通过 register_channel() 注入自身引用。
    """

    gateway: Gateway | None

    def __init__(self):
        self.gateway = None

    @abstractmethod
    def get_channel_id(self) -> str:
        """返回 channel 标识"""
        pass

    @abstractmethod
    async def start(self) -> None:
        """启动 channel"""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """停止 channel"""
        pass

    @abstractmethod
    async def send_event(self, event: EventEnvelope) -> None:
        """接收来自 Gateway 的事件"""
        pass

    def event_filter(self) -> set[str] | None:
        """此 Channel 关心的事件类型集合。None = 全部（默认，向后兼容）。"""
        return None


@runtime_checkable
class OutboundCapable(Protocol):
    """支持主动发送消息的 Channel 协议"""

    async def send_outbound(
        self, target: str, text: str, msg_type: str = "card",
    ) -> dict:
        """向指定目标发送消息。返回 {success, message_id, ...}"""
        ...
