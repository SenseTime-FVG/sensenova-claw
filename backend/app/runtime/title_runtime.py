from __future__ import annotations

import asyncio
import contextlib
import logging

from app.db.repository import Repository
from app.events.envelope import EventEnvelope
from app.events.types import UI_USER_INPUT
from app.llm.factory import LLMFactory
from app.runtime.publisher import EventPublisher

logger = logging.getLogger(__name__)

AGENT_UPDATE_TITLE_STARTED = "agent.update_title_started"
AGENT_UPDATE_TITLE_COMPLETED = "agent.update_title_completed"


class TitleRuntime:
    def __init__(self, publisher: EventPublisher, repo: Repository):
        self.publisher = publisher
        self.repo = repo
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
        async for event in self.publisher.bus.subscribe():
            if event.type == UI_USER_INPUT:
                await self._handle_user_input(event)

    async def _handle_user_input(self, event: EventEnvelope) -> None:
        session_id = event.session_id
        if session_id in self._processed_sessions:
            return

        self._processed_sessions.add(session_id)
        content = str(event.payload.get("content", ""))

        await self.publisher.publish(
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
            provider = self.llm_factory.get_provider()
            messages = [
                {
                    "role": "system",
                    "content": "你是一个会话标题生成助手。根据用户的第一个问题，生成一个简短的会话标题（不超过10个字）。只返回标题文本，不要有其他内容。",
                },
                {"role": "user", "content": f"用户问题：{user_input}\n\n请生成会话标题："},
            ]

            response = await provider.chat(messages=messages, tools=[], temperature=0.7)
            title = response.get("content", "").strip()

            if len(title) > 10:
                title = title[:10]

            if title:
                await self.repo.update_session_title(session_id, title)
                logger.info(f"Generated title for session {session_id}: {title}")

                await self.publisher.publish(
                    EventEnvelope(
                        type=AGENT_UPDATE_TITLE_COMPLETED,
                        session_id=session_id,
                        source="title",
                        payload={"title": title, "success": True},
                    )
                )
        except Exception as exc:
            logger.warning(f"Failed to generate session title: {exc}")
            await self.publisher.publish(
                EventEnvelope(
                    type=AGENT_UPDATE_TITLE_COMPLETED,
                    session_id=session_id,
                    source="title",
                    payload={"title": "", "success": False, "error": str(exc)},
                )
            )
