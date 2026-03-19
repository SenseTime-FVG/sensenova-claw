"""通知 provider 抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from agentos.kernel.notification.models import Notification


class NotificationProvider(ABC):
    """通知 provider 抽象。"""

    channel_name: str = ""

    @abstractmethod
    async def send(self, notification: Notification) -> bool:
        """发送通知，返回是否成功。"""
        raise NotImplementedError
