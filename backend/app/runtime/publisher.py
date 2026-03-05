from __future__ import annotations

import logging

from app.db.repository import Repository
from app.events.bus import PublicEventBus
from app.events.envelope import EventEnvelope

logger = logging.getLogger(__name__)


class EventPublisher:
    def __init__(self, bus: PublicEventBus, repo: Repository):
        self.bus = bus
        self.repo = repo

    async def publish(self, event: EventEnvelope) -> None:
        # 所有事件先落库再广播，保证可追溯。
        await self.repo.log_event(event)
        logger.debug("event persisted: %s", event.type)
        await self.bus.publish(event)
