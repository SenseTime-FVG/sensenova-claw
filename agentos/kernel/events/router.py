from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable

from agentos.kernel.events.bus import PrivateEventBus, PublicEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import USER_INPUT

logger = logging.getLogger(__name__)


class BusRouter:
    """事件路由器 + 私有总线生命周期管理

    职责：
    1. 订阅 PublicEventBus，按 session_id 路由到对应 PrivateEventBus
    2. 首次遇到 USER_INPUT 时创建 PrivateEventBus 并通知 Worker 工厂
    3. GC 回收超时未活跃的私有总线
    """

    def __init__(
        self,
        public_bus: PublicEventBus,
        ttl_seconds: float = 3600,
        gc_interval: float = 60,
    ):
        self._public_bus = public_bus
        self._private_buses: dict[str, PrivateEventBus] = {}
        self._last_active: dict[str, float] = {}
        self._ttl_seconds = ttl_seconds
        self._gc_interval = gc_interval
        self._route_task: asyncio.Task | None = None
        self._gc_task: asyncio.Task | None = None
        self._worker_factories: list[Callable[[str, PrivateEventBus], Awaitable[None]]] = []
        self._on_destroy_callbacks: list[Callable[[str], Awaitable[None]]] = []
        # PrivateEventBus 回流到 PublicEventBus 时标记 event_id，
        # BusRouter 路由时跳过这些事件，防止 Worker 重复收到。
        self._forwarded_ids: set[str] = set()

    @property
    def public_bus(self) -> PublicEventBus:
        return self._public_bus

    def get_or_create(self, session_id: str) -> PrivateEventBus:
        """惰性创建私有总线"""
        if session_id not in self._private_buses:
            self._private_buses[session_id] = PrivateEventBus(
                session_id=session_id,
                public_bus=self._public_bus,
                on_forward=self._mark_forwarded,
            )
            logger.info("Created PrivateEventBus for session %s", session_id)
        self._last_active[session_id] = time.time()
        return self._private_buses[session_id]

    def _mark_forwarded(self, event_id: str) -> None:
        """PrivateEventBus 回流事件时调用，标记 event_id 避免重复路由"""
        self._forwarded_ids.add(event_id)

    def get(self, session_id: str) -> PrivateEventBus | None:
        """获取已存在的私有总线"""
        bus = self._private_buses.get(session_id)
        if bus:
            self._last_active[session_id] = time.time()
        return bus

    def register_worker_factory(
        self, factory: Callable[[str, PrivateEventBus], Awaitable[None]]
    ) -> None:
        """注册 Worker 工厂回调（Runtime 调用）"""
        self._worker_factories.append(factory)

    def on_destroy(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """注册销毁回调（Runtime 用来清理 Worker）"""
        self._on_destroy_callbacks.append(callback)

    async def destroy(self, session_id: str) -> None:
        """销毁私有总线，通知所有注册的回调"""
        bus = self._private_buses.pop(session_id, None)
        self._last_active.pop(session_id, None)
        if bus:
            bus.close()
            for cb in self._on_destroy_callbacks:
                try:
                    await cb(session_id)
                except Exception:
                    logger.exception("Error in destroy callback for session %s", session_id)
            logger.info("Destroyed PrivateEventBus for session %s", session_id)

    def touch(self, session_id: str) -> None:
        """刷新活跃时间"""
        if session_id in self._last_active:
            self._last_active[session_id] = time.time()

    async def start(self) -> None:
        """启动路由循环和 GC 循环"""
        self._route_task = asyncio.create_task(self._route_loop())
        self._gc_task = asyncio.create_task(self._gc_loop())
        logger.info("BusRouter started (ttl=%ds, gc_interval=%ds)", self._ttl_seconds, self._gc_interval)

    async def stop(self) -> None:
        """停止路由和 GC，销毁所有私有总线"""
        for task in [self._route_task, self._gc_task]:
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        for sid in list(self._private_buses):
            await self.destroy(sid)
        logger.info("BusRouter stopped")

    async def _route_loop(self) -> None:
        """订阅 PublicEventBus，将事件路由到对应的私有总线"""
        async for event in self._public_bus.subscribe():
            if not event.session_id:
                continue
            # system.* 事件不路由到私有总线
            if event.type.startswith("system."):
                continue

            # 跳过从 PrivateEventBus 回流的事件：
            # 这些事件已经在 PrivateEventBus.publish() 中投递给了私有订阅者，
            # 不需要再通过 deliver() 重复投递。
            if event.event_id in self._forwarded_ids:
                self._forwarded_ids.discard(event.event_id)
                continue

            bus = self._private_buses.get(event.session_id)
            if not bus:
                # 首次遇到此 session 的事件：创建 PrivateEventBus 并通知工厂创建 Worker
                if event.type == USER_INPUT:
                    bus = self.get_or_create(event.session_id)
                    for factory in self._worker_factories:
                        try:
                            await factory(event.session_id, bus)
                        except Exception:
                            logger.exception(
                                "Worker factory failed for session %s", event.session_id
                            )
                    # 让 Worker 的 subscribe() 有机会注册队列
                    await asyncio.sleep(0)
                else:
                    # 非 USER_INPUT 且无现有总线，跳过
                    continue

            # 使用 deliver（不回流），防止 Public → Private → Public 无限循环
            await bus.deliver(event)

    async def _gc_loop(self) -> None:
        """定期清理超时未活跃的私有总线"""
        while True:
            await asyncio.sleep(self._gc_interval)
            now = time.time()
            expired = [
                sid
                for sid, last in self._last_active.items()
                if now - last > self._ttl_seconds
            ]
            for sid in expired:
                logger.info("GC: cleaning up session %s (inactive > %ds)", sid, self._ttl_seconds)
                await self.destroy(sid)
