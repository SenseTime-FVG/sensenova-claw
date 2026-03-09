from abc import ABC, abstractmethod

from app.events.envelope import EventEnvelope


class Channel(ABC):
    """Channel 抽象基类"""

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
