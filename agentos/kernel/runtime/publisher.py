from __future__ import annotations

import logging

from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.events.envelope import EventEnvelope

logger = logging.getLogger(__name__)


class EventPublisher:
    """入口事件发布器：Gateway 用来发布用户输入等入口事件到 PublicEventBus

    持久化由独立的 EventPersister 订阅 PublicEventBus 完成。
    """

    def __init__(self, bus: PublicEventBus):
        self.bus = bus

    async def publish(self, event: EventEnvelope) -> None:
        await self.bus.publish(event)
