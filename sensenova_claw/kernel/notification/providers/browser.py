"""浏览器通知 provider。

通过事件总线发布 notification.push，由 WebSocket Channel 转发给前端。
"""

from __future__ import annotations

from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import NOTIFICATION_PUSH
from sensenova_claw.kernel.notification.models import Notification
from sensenova_claw.kernel.notification.providers.base import NotificationProvider


class BrowserNotificationProvider(NotificationProvider):
    """浏览器推送通知。"""

    channel_name = "browser"

    def __init__(self, bus: PublicEventBus):
        self._bus = bus

    async def send(self, notification: Notification) -> bool:
        await self._bus.publish(
            EventEnvelope(
                type=NOTIFICATION_PUSH,
                session_id=notification.session_id or "system",
                source="notification",
                payload={
                    "id": notification.id,
                    "title": notification.title,
                    "body": notification.body,
                    "level": notification.level,
                    "source": notification.source,
                    "session_id": notification.session_id,
                    "actions": notification.actions,
                    "metadata": notification.metadata or {},
                    "created_at_ms": notification.created_at_ms,
                },
            )
        )
        return True
