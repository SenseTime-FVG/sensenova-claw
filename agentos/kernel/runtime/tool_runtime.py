from __future__ import annotations

import logging
from typing import Any

from agentos.kernel.events.bus import PrivateEventBus
from agentos.kernel.events.router import BusRouter
from agentos.kernel.runtime.workers.tool_worker import ToolSessionWorker
from agentos.platform.security.path_policy import PathPolicy
from agentos.capabilities.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolRuntime:
    """全局单例管理者：持有 ToolRegistry，管理 ToolSessionWorker 生命周期"""

    def __init__(self, bus_router: BusRouter, registry: ToolRegistry,
                 path_policy: PathPolicy | None = None,
                 agent_registry: Any = None,
                 workflow_registry: Any = None):
        self.bus_router = bus_router
        self.registry = registry
        self.path_policy = path_policy
        self.agent_registry = agent_registry
        self.workflow_registry = workflow_registry
        self._workers: dict[str, ToolSessionWorker] = {}

    async def start(self) -> None:
        self.bus_router.register_worker_factory(self._create_worker)
        self.bus_router.on_destroy(self._on_session_destroy)

    async def stop(self) -> None:
        for worker in self._workers.values():
            await worker.stop()
        self._workers.clear()

    async def _create_worker(self, session_id: str, private_bus: PrivateEventBus) -> None:
        """Worker 工厂：BusRouter 首次遇到 session 时调用"""
        worker = ToolSessionWorker(
            session_id=session_id,
            private_bus=private_bus,
            runtime=self,
        )
        self._workers[session_id] = worker
        await worker.start()
        logger.info("Created ToolSessionWorker for session %s", session_id)

    async def _on_session_destroy(self, session_id: str) -> None:
        """GC 回调：清理 Worker"""
        worker = self._workers.pop(session_id, None)
        if worker:
            await worker.stop()
            logger.info("Cleaned up ToolSessionWorker for session %s", session_id)
