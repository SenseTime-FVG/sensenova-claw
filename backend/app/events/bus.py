from __future__ import annotations

import asyncio
import logging
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


class PrivateEventBus:
    """会话私有总线，物理隔离单个 session 的事件流"""

    def __init__(self, session_id: str, public_bus: PublicEventBus):
        self.session_id = session_id
        self._public_bus = public_bus
        self._subscribers: set[asyncio.Queue[EventEnvelope]] = set()
        self._closed = False

    async def publish(self, event: EventEnvelope) -> None:
        """发布事件：分发给私有订阅者，再回流到公共总线"""
        # 1. 分发给本总线的所有私有订阅者
        for q in list(self._subscribers):
            await q.put(event)
        # 2. 回流到 PublicEventBus（供 Gateway、持久化、监控消费）
        await self._public_bus.publish(event)

    async def deliver(self, event: EventEnvelope) -> None:
        """直接投递到私有订阅者，不回流（BusRouter 调用，防止循环）"""
        for q in list(self._subscribers):
            await q.put(event)

    async def subscribe(self) -> AsyncIterator[EventEnvelope]:
        """订阅私有事件流（Worker 调用）"""
        queue: asyncio.Queue[EventEnvelope] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            while not self._closed:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)

    def close(self) -> None:
        """关闭总线，停止所有订阅者"""
        self._closed = True
