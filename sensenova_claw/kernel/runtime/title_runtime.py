from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

from sensenova_claw.adapters.storage.repository import Repository
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import USER_INPUT
from sensenova_claw.adapters.llm.factory import LLMFactory

if TYPE_CHECKING:
    from sensenova_claw.capabilities.agents.registry import AgentRegistry

logger = logging.getLogger(__name__)

from sensenova_claw.kernel.events.types import AGENT_UPDATE_TITLE_COMPLETED

AGENT_UPDATE_TITLE_STARTED = "agent.update_title_started"


class TitleRuntime:
    """TitleRuntime 直接订阅 PublicEventBus，不使用 Worker 模式

    标题生成是一次性操作，不需要 per-session Worker。
    """

    def __init__(
        self,
        bus: PublicEventBus,
        repo: Repository,
        agent_registry: AgentRegistry | None = None,
    ):
        self.bus = bus
        self.repo = repo
        self.agent_registry = agent_registry
        self.llm_factory = LLMFactory()
        self._task: asyncio.Task | None = None
        self._processed_sessions: set[str] = set()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _loop(self) -> None:
        async for event in self.bus.subscribe():
            if event.type == USER_INPUT:
                await self._handle_user_input(event)

    async def _handle_user_input(self, event: EventEnvelope) -> None:
        session_id = event.session_id
        if session_id in self._processed_sessions:
            return

        # 检查 session 是否已有标题，有则跳过
        meta = await self.repo.get_session_meta(session_id)
        existing_title = (meta or {}).get("title", "")
        if existing_title and existing_title != "未命名会话":
            self._processed_sessions.add(session_id)
            return

        self._processed_sessions.add(session_id)
        content = str(event.payload.get("content", ""))

        await self.bus.publish(
            EventEnvelope(
                type=AGENT_UPDATE_TITLE_STARTED,
                session_id=session_id,
                source="title",
                payload={"user_input": content},
            )
        )

        asyncio.create_task(self._generate_title(session_id, content))

    async def _generate_title(self, session_id: str, user_input: str) -> None:
        try:
            provider_name, model = await self._resolve_session_model(session_id)
            provider = self.llm_factory.get_provider(provider_name)
            messages = [
                {
                    "role": "system",
                    "content": "你是一个会话标题生成助手。根据用户的第一个问题，生成一个简短的会话标题（不超过10个字）。只返回标题文本，不要有其他内容。",
                },
                {"role": "user", "content": f"用户问题：{user_input}\n\n请生成会话标题："},
            ]

            response = await provider.call(model=model, messages=messages, tools=None, temperature=1.0)
            title = response.get("content", "").strip()

            if len(title) > 10:
                title = title[:10]

            if title:
                await self.repo.update_session_title(session_id, title)
                logger.info("Generated title for session %s: %s", session_id, title)

                await self.bus.publish(
                    EventEnvelope(
                        type=AGENT_UPDATE_TITLE_COMPLETED,
                        session_id=session_id,
                        source="title",
                        payload={"title": title, "success": True},
                    )
                )
        except Exception as exc:
            logger.warning("Failed to generate session title: %s", exc)
            await self.bus.publish(
                EventEnvelope(
                    type=AGENT_UPDATE_TITLE_COMPLETED,
                    session_id=session_id,
                    source="title",
                    payload={"title": "", "success": False, "error": str(exc)},
                )
            )

    async def _resolve_session_model(self, session_id: str) -> tuple[str, str]:
        """优先使用 session 绑定的 agent 模型，缺失时回退到全局默认模型。"""
        from sensenova_claw.platform.config.config import config

        model_key: str | None = None
        if self.agent_registry:
            session_meta = await self.repo.get_session_meta(session_id)
            agent_id = (session_meta or {}).get("agent_id")
            agent_config = self.agent_registry.get(agent_id) if agent_id else None
            if agent_config and agent_config.model:
                model_key = agent_config.model

        provider_name, model_id = config.resolve_model(model_key)

        # 兼容仍直接填写 model_id 的 agent 配置。
        if provider_name == "mock" and model_key:
            return "mock", model_key
        return provider_name, model_id
