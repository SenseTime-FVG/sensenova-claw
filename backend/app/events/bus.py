from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import AsyncIterator

from app.events.envelope import EventEnvelope

logger = logging.getLogger(__name__)


class PublicEventBus:
    def __init__(self):
        self._subscribers: set[asyncio.Queue[EventEnvelope]] = set()

    async def publish(self, event: EventEnvelope) -> None:
        logger.debug("publish event: %s session=%s turn=%s payload=%s", event.type, event.session_id, event.turn_id, event.payload)
        for q in list(self._subscribers):
            await q.put(event)

    async def subscribe(self) -> AsyncIterator[EventEnvelope]:
        queue: asyncio.Queue[EventEnvelope] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)


class PrivateBusManager:
    def __init__(self):
        self._session_queues: defaultdict[str, asyncio.Queue[EventEnvelope]] = defaultdict(asyncio.Queue)

    async def publish(self, event: EventEnvelope) -> None:
        await self._session_queues[event.session_id].put(event)

    async def get(self, session_id: str) -> EventEnvelope:
        return await self._session_queues[session_id].get()
