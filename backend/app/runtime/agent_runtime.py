from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid

from app.core.config import config
from app.db.repository import Repository
from app.events.envelope import EventEnvelope
from app.events.types import (
    AGENT_STEP_COMPLETED,
    AGENT_STEP_STARTED,
    LLM_CALL_COMPLETED,
    LLM_CALL_REQUESTED,
    TOOL_CALL_COMPLETED,
    TOOL_CALL_REQUESTED,
    UI_USER_INPUT,
)
from app.runtime.context_builder import ContextBuilder
from app.runtime.publisher import EventPublisher
from app.runtime.state import SessionStateStore, TurnState
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class AgentRuntime:
    def __init__(
        self,
        publisher: EventPublisher,
        repo: Repository,
        context_builder: ContextBuilder,
        tool_registry: ToolRegistry,
        state_store: SessionStateStore,
    ):
        self.publisher = publisher
        self.repo = repo
        self.context_builder = context_builder
        self.tool_registry = tool_registry
        self.state_store = state_store
        self._task: asyncio.Task | None = None

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
            elif event.type == LLM_CALL_COMPLETED:
                await self._handle_llm_completed(event)
            elif event.type == TOOL_CALL_COMPLETED:
                await self._handle_tool_completed(event)

    async def _handle_user_input(self, event: EventEnvelope) -> None:
        content = str(event.payload.get("content", ""))
        session_id = event.session_id
        turn_id = event.turn_id or f"turn_{uuid.uuid4().hex[:12]}"

        await self.repo.create_session(session_id, meta={"title": content[:20] or "新会话"})
        await self.repo.update_session_activity(session_id)
        await self.repo.create_turn(turn_id=turn_id, session_id=session_id, user_input=content)

        messages = self.context_builder.build_messages(content)
        state = TurnState(turn_id=turn_id, user_input=content, messages=messages)
        self.state_store.set_turn(session_id, state)

        await self.publisher.publish(
            EventEnvelope(
                type=AGENT_STEP_STARTED,
                session_id=session_id,
                turn_id=turn_id,
                source="agent",
                payload={"step_type": "llm_call", "description": "开始处理用户输入"},
            )
        )

        llm_call_id = f"llm_{uuid.uuid4().hex[:12]}"
        await self.publisher.publish(
            EventEnvelope(
                type=LLM_CALL_REQUESTED,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=llm_call_id,
                source="agent",
                payload={
                    "llm_call_id": llm_call_id,
                    "provider": config.get("agent.provider", "mock"),
                    "model": config.get("agent.default_model"),
                    "messages": messages,
                    "tools": self.tool_registry.as_llm_tools(),
                    "temperature": config.get("agent.default_temperature", 0.2),
                },
            )
        )

    async def _handle_llm_completed(self, event: EventEnvelope) -> None:
        if not event.turn_id:
            return
        state = self.state_store.get_turn(event.session_id, event.turn_id)
        if not state:
            return

        response = event.payload.get("response", {})
        finish_reason = event.payload.get("finish_reason", "stop")
        content = response.get("content", "")
        tool_calls = response.get("tool_calls", [])

        state.messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})

        if finish_reason == "tool_calls":
            if not tool_calls:
                logger.warning("finish_reason is tool_calls but tool_calls is empty, treating as stop")
                finish_reason = "stop"

        if finish_reason == "tool_calls" and tool_calls:
            state.pending_tool_calls = {call["id"] for call in tool_calls}
            for call in tool_calls:
                await self.publisher.publish(
                    EventEnvelope(
                        type=TOOL_CALL_REQUESTED,
                        session_id=event.session_id,
                        turn_id=event.turn_id,
                        trace_id=call["id"],
                        source="agent",
                        payload={
                            "tool_call_id": call["id"],
                            "tool_name": call["name"],
                            "arguments": call.get("arguments", {}),
                        },
                    )
                )
            return

        state.final_response = content
        await self.repo.complete_turn(event.turn_id, agent_response=content)
        await self.publisher.publish(
            EventEnvelope(
                type=AGENT_STEP_COMPLETED,
                session_id=event.session_id,
                turn_id=event.turn_id,
                source="agent",
                payload={
                    "step_type": "final",
                    "result": {"content": content},
                    "next_action": "end",
                },
            )
        )

    async def _handle_tool_completed(self, event: EventEnvelope) -> None:
        if not event.turn_id:
            return
        state = self.state_store.get_turn(event.session_id, event.turn_id)
        if not state:
            return

        tool_call_id = event.payload.get("tool_call_id")
        if tool_call_id in state.pending_tool_calls:
            state.pending_tool_calls.remove(tool_call_id)

        tool_name = str(event.payload.get("tool_name"))
        result = event.payload.get("result")
        state.tool_results.append({"tool_name": tool_name, "result": result})
        state.messages = self.context_builder.append_tool_result(
            state.messages,
            tool_name=tool_name,
            result=result,
            tool_call_id=str(tool_call_id) if tool_call_id else None,
        )

        if state.pending_tool_calls:
            return

        llm_call_id = f"llm_{uuid.uuid4().hex[:12]}"
        await self.publisher.publish(
            EventEnvelope(
                type=LLM_CALL_REQUESTED,
                session_id=event.session_id,
                turn_id=event.turn_id,
                trace_id=llm_call_id,
                source="agent",
                payload={
                    "llm_call_id": llm_call_id,
                    "provider": config.get("agent.provider", "mock"),
                    "model": config.get("agent.default_model"),
                    "messages": state.messages,
                    "tools": self.tool_registry.as_llm_tools(),
                    "temperature": config.get("agent.default_temperature", 0.2),
                },
            )
        )
