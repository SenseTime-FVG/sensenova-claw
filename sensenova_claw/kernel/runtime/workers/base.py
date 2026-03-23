from __future__ import annotations

import asyncio
import contextlib
import logging

from sensenova_claw.kernel.events.bus import PrivateEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope

logger = logging.getLogger(__name__)


class SessionWorker:
    """会话级 Worker 基类

    每个 Worker 订阅 PrivateEventBus，处理单个 session 的事件。
    不持有独立资源，通过 self.rt 引用父 Runtime 的共享资源。
    """

    def __init__(self, session_id: str, private_bus: PrivateEventBus):
        self.session_id = session_id
        self.bus = private_bus
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _loop(self) -> None:
        try:
            async for event in self.bus.subscribe():
                try:
                    await self._handle(event)
                except Exception:
                    logger.exception(
                        "[%s] Error handling event %s in session %s",
                        self.__class__.__name__,
                        event.type,
                        self.session_id,
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "[%s] Worker loop crashed for session %s",
                self.__class__.__name__,
                self.session_id,
            )

    async def _handle(self, event: EventEnvelope) -> None:
        raise NotImplementedError
