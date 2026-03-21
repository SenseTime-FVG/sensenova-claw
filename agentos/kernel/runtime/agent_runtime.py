from __future__ import annotations

import logging
import uuid
from typing import Any, TYPE_CHECKING

from agentos.adapters.storage.repository import Repository
from agentos.adapters.storage.session_jsonl import SessionJsonlWriter
from agentos.kernel.events.bus import PrivateEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import USER_INPUT
from agentos.kernel.events.router import BusRouter
from agentos.kernel.runtime.context_builder import ContextBuilder
from agentos.kernel.runtime.context_compressor import ContextCompressor
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
        jsonl_writer: SessionJsonlWriter | None = None,
        context_compressor: ContextCompressor | None = None,
    ):
        self.bus_router = bus_router
        self.repo = repo
        self.context_builder = context_builder
        self.tool_registry = tool_registry
        self.state_store = state_store
        self.agent_registry = agent_registry
        self.memory_manager = memory_manager  # 可能为 None（记忆系统未启用）
        self.jsonl_writer = jsonl_writer  # 可能为 None（JSONL 导出未启用）
        self.context_compressor = context_compressor  # 可能为 None（上下文压缩未启用）
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
        """GC 回调：清理 Worker 及相关资源"""
        worker = self._workers.pop(session_id, None)
        if worker:
            await worker.stop()
            logger.info("Cleaned up AgentSessionWorker for session %s", session_id)
        # 清理上下文压缩器中该会话的锁，防止内存泄漏
        if self.context_compressor:
            self.context_compressor.cleanup_session(session_id)

    async def spawn_agent_session(
        self,
        agent_id: str,
        session_id: str,
        user_input: str,
        parent_session_id: str | None = None,
        meta: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> str:
        """创建目标 Agent 会话并注入首条 USER_INPUT。"""
        session_meta = dict(meta or {})
        session_meta.setdefault("agent_id", agent_id)
        if parent_session_id:
            session_meta.setdefault("parent_session_id", parent_session_id)
        await self.repo.create_session(session_id=session_id, meta=session_meta)
        logger.info(
            "spawn agent session session=%s agent=%s parent_session=%s trace=%s",
            session_id,
            agent_id,
            parent_session_id,
            trace_id,
        )
        return await self.send_user_input(
            session_id=session_id,
            user_input=user_input,
            extra_payload={
                key: value
                for key, value in session_meta.items()
                if key in {"send_depth", "send_chain"}
            },
            trace_id=trace_id,
        )

    async def send_user_input(
        self,
        session_id: str,
        user_input: str,
        extra_payload: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> str:
        """向指定会话注入一条 USER_INPUT。"""
        turn_id = f"turn_{uuid.uuid4().hex[:12]}"
        payload = {"content": user_input}
        if extra_payload:
            payload.update(extra_payload)
        await self.bus_router.public_bus.publish(
            EventEnvelope(
                type=USER_INPUT,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="agent_runtime",
                payload=payload,
            )
        )
        logger.info(
            "send user input session=%s turn=%s trace=%s payload_keys=%s",
            session_id,
            turn_id,
            trace_id,
            sorted(payload.keys()),
        )
        return turn_id
