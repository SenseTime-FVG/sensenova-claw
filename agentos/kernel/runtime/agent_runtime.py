from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from agentos.adapters.storage.repository import Repository
from agentos.kernel.events.bus import PrivateEventBus
from agentos.kernel.events.router import BusRouter
from agentos.kernel.runtime.context_builder import ContextBuilder
from agentos.kernel.runtime.state import SessionStateStore
from agentos.kernel.runtime.workers.agent_worker import AgentSessionWorker
from agentos.capabilities.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from agentos.capabilities.agents.registry import AgentRegistry

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
        agent_registry: AgentRegistry | None = None,
        memory_manager: Any = None,
    ):
        self.bus_router = bus_router
        self.repo = repo
        self.context_builder = context_builder
        self.tool_registry = tool_registry
        self.state_store = state_store
        self.agent_registry = agent_registry
        self.memory_manager = memory_manager  # 可能为 None（记忆系统未启用）
        self._workers: dict[str, AgentSessionWorker] = {}

    async def start(self) -> None:
        self.bus_router.register_worker_factory(self._create_worker)
        self.bus_router.on_destroy(self._on_session_destroy)

    async def stop(self) -> None:
        for worker in self._workers.values():
            await worker.stop()
        self._workers.clear()

    async def _create_worker(self, session_id: str, private_bus: PrivateEventBus) -> None:
        """Worker 工厂：BusRouter 首次遇到 session 时调用

        根据 session meta 中的 agent_id 查找对应 AgentConfig，
        使 Worker 使用该 Agent 的独立配置。
        """
        agent_config = None
        if self.agent_registry:
            session_meta = await self.repo.get_session_meta(session_id)
            agent_id = (session_meta or {}).get("agent_id", "default")
            agent_config = self.agent_registry.get(agent_id)
            # 找不到则回退到 default
            if not agent_config:
                agent_config = self.agent_registry.get("default")

        worker = AgentSessionWorker(
            session_id=session_id,
            private_bus=private_bus,
            runtime=self,
            agent_config=agent_config,
        )
        self._workers[session_id] = worker
        await worker.start()
        logger.info(
            "Created AgentSessionWorker for session %s (agent=%s)",
            session_id,
            agent_config.id if agent_config else "default",
        )

    async def _on_session_destroy(self, session_id: str) -> None:
        """GC 回调：清理 Worker"""
        worker = self._workers.pop(session_id, None)
        if worker:
            await worker.stop()
            logger.info("Cleaned up AgentSessionWorker for session %s", session_id)
