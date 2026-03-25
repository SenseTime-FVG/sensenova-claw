from __future__ import annotations

import logging

from sensenova_claw.kernel.events.bus import PrivateEventBus
from sensenova_claw.kernel.events.router import BusRouter
from sensenova_claw.adapters.llm.factory import LLMFactory
from sensenova_claw.kernel.runtime.state import SessionStateStore
from sensenova_claw.kernel.runtime.workers.llm_worker import LLMSessionWorker

logger = logging.getLogger(__name__)


class LLMRuntime:
    """全局单例管理者：持有 LLMFactory，管理 LLMSessionWorker 生命周期"""

    def __init__(
        self,
        bus_router: BusRouter,
        factory: LLMFactory,
        state_store: SessionStateStore | None = None,
    ):
        self.bus_router = bus_router
        self.factory = factory
        self.state_store = state_store
        self._workers: dict[str, LLMSessionWorker] = {}

    async def start(self) -> None:
        self.bus_router.register_worker_factory(self._create_worker)
        self.bus_router.on_destroy(self._on_session_destroy)

    async def stop(self) -> None:
        for worker in self._workers.values():
            await worker.stop()
        self._workers.clear()

    async def _create_worker(self, session_id: str, private_bus: PrivateEventBus) -> None:
        """Worker 工厂：BusRouter 首次遇到 session 时调用"""
        worker = LLMSessionWorker(
            session_id=session_id,
            private_bus=private_bus,
            runtime=self,
        )
        self._workers[session_id] = worker
        await worker.start()
        logger.info("Created LLMSessionWorker for session %s", session_id)

    async def _on_session_destroy(self, session_id: str) -> None:
        """GC 回调：清理 Worker"""
        worker = self._workers.pop(session_id, None)
        if worker:
            await worker.stop()
            logger.info("Cleaned up LLMSessionWorker for session %s", session_id)
