from __future__ import annotations

import asyncio
import contextlib
import logging

from app.events.envelope import EventEnvelope
from app.gateway.base import Channel
from app.runtime.publisher import EventPublisher

logger = logging.getLogger(__name__)


class Gateway:
    """Gateway 负责管理多个 Channel 并在它们之间路由事件"""

    def __init__(self, publisher: EventPublisher):
        self.publisher = publisher
        self._channels: dict[str, Channel] = {}
        self._session_bindings: dict[str, str] = {}  # session_id -> channel_id
        self._task: asyncio.Task | None = None

    def register_channel(self, channel: Channel) -> None:
        """注册一个 Channel"""
        channel_id = channel.get_channel_id()
        self._channels[channel_id] = channel
        logger.info(f"Registered channel: {channel_id}")

    def bind_session(self, session_id: str, channel_id: str) -> None:
        """绑定 session 到 Channel"""
        self._session_bindings[session_id] = channel_id

    def unbind_session(self, session_id: str) -> None:
        """解绑 session"""
        self._session_bindings.pop(session_id, None)

    async def publish_from_channel(self, event: EventEnvelope) -> None:
        """从 Channel 接收事件并发布到 PublicEventBus"""
        await self.publisher.publish(event)

    async def start(self) -> None:
        """启动 Gateway 和所有 Channel"""
        for channel in self._channels.values():
            await channel.start()
        self._task = asyncio.create_task(self._loop())
        logger.info("Gateway started")

    async def stop(self) -> None:
        """停止 Gateway 和所有 Channel"""
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        for channel in self._channels.values():
            await channel.stop()
        logger.info("Gateway stopped")

    async def _loop(self) -> None:
        """订阅 PublicEventBus 并分发事件到对应的 Channel"""
        async for event in self.publisher.bus.subscribe():
            await self._dispatch_event(event)

    async def _dispatch_event(self, event: EventEnvelope) -> None:
        """将事件分发到对应的 Channel"""
        if not event.session_id:
            return

        channel_id = self._session_bindings.get(event.session_id)
        if not channel_id:
            return

        channel = self._channels.get(channel_id)
        if not channel:
            return

        try:
            await channel.send_event(event)
        except Exception as exc:
            logger.error(f"Failed to send event to channel {channel_id}: {exc}")
