from __future__ import annotations

import asyncio
import contextlib
import logging

from agentos.adapters.storage.repository import Repository
from agentos.kernel.events.bus import PublicEventBus

logger = logging.getLogger(__name__)


class EventPersister:
    """订阅 PublicEventBus，将所有事件持久化到数据库"""

    def __init__(self, bus: PublicEventBus, repo: Repository):
        self._bus = bus
        self._repo = repo
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())
        logger.info("EventPersister started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("EventPersister stopped")

    async def _loop(self) -> None:
        async for event in self._bus.subscribe():
            try:
                await self._repo.log_event(event)
                logger.debug("event persisted: %s", event.type)
            except Exception:
                logger.exception("Failed to persist event: %s", event.event_id)
