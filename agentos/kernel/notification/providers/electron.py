"""Electron 通知 provider 占位实现。"""

from __future__ import annotations

import logging

from agentos.kernel.notification.models import Notification
from agentos.kernel.notification.providers.base import NotificationProvider

logger = logging.getLogger(__name__)


class ElectronNotificationProvider(NotificationProvider):
    """Electron IPC 通知占位。"""

    channel_name = "electron"

    async def send(self, notification: Notification) -> bool:
        logger.warning("Electron notification provider 尚未实现: %s", notification.title)
        return False
