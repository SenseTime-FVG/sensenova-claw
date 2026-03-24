"""会话内通知 provider。"""

from __future__ import annotations

from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import NOTIFICATION_SESSION
from sensenova_claw.kernel.notification.models import Notification
from sensenova_claw.kernel.notification.providers.base import NotificationProvider


class SessionNotificationProvider(NotificationProvider):
    """将通知作为会话内系统事件推送。"""

    channel_name = "session"

    def __init__(self, bus: PublicEventBus):
        self._bus = bus

    async def send(self, notification: Notification) -> bool:
        if not notification.session_id:
            return False

        await self._bus.publish(
            EventEnvelope(
                type=NOTIFICATION_SESSION,
                session_id=notification.session_id,
                source="notification",
                payload={
                    "id": notification.id,
                    "title": notification.title,
                    "body": notification.body,
                    "level": notification.level,
                    "source": notification.source,
                    "actions": notification.actions,
                    "metadata": notification.metadata or {},
                    "created_at_ms": notification.created_at_ms,
                },
            )
        )
        return True
