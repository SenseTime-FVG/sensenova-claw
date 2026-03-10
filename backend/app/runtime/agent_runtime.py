from __future__ import annotations

import logging

from app.db.repository import Repository
from app.events.bus import PrivateEventBus
from app.events.router import BusRouter
from app.runtime.context_builder import ContextBuilder
from app.runtime.state import SessionStateStore
from app.runtime.workers.agent_worker import AgentSessionWorker
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class AgentRuntime:
    """全局单例管理者：持有共享资源，管理 AgentSessionWorker 生命周期"""

    def __init__(
        self,
        bus_router: BusRouter,
        repo: Repository,
        context_builder: ContextBuilder,
        tool_registry: ToolRegistry,
        state_store: SessionStateStore,
    ):
        self.bus_router = bus_router
        self.repo = repo
        self.context_builder = context_builder
        self.tool_registry = tool_registry
        self.state_store = state_store
        self._workers: dict[str, AgentSessionWorker] = {}

    async def start(self) -> None:
        self.bus_router.register_worker_factory(self._create_worker)
        self.bus_router.on_destroy(self._on_session_destroy)

    async def stop(self) -> None:
        for worker in self._workers.values():
            await worker.stop()
        self._workers.clear()

    async def _create_worker(self, session_id: str, private_bus: PrivateEventBus) -> None:
        """Worker 工厂：BusRouter 首次遇到 session 时调用"""
        worker = AgentSessionWorker(
            session_id=session_id,
            private_bus=private_bus,
            runtime=self,
        )
        self._workers[session_id] = worker
        await worker.start()
        logger.info("Created AgentSessionWorker for session %s", session_id)

    async def _on_session_destroy(self, session_id: str) -> None:
        """GC 回调：清理 Worker"""
        worker = self._workers.pop(session_id, None)
        if worker:
            await worker.stop()
            logger.info("Cleaned up AgentSessionWorker for session %s", session_id)
