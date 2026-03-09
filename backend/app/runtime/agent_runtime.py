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
    LLM_CALL_RESULT,
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
            elif event.type == LLM_CALL_RESULT:
                await self._handle_llm_result(event)
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

        # 获取历史消息
        history = self.state_store.get_session_history(session_id)
        messages = self.context_builder.build_messages(content, history)
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

    async def _handle_llm_result(self, event: EventEnvelope) -> None:
        """处理LLM返回的结果"""
        if not event.turn_id:
            return
        state = self.state_store.get_turn(event.session_id, event.turn_id)
        if not state:
            return

        response = event.payload.get("response", {})
        content = response.get("content", "")
        tool_calls = response.get("tool_calls", [])

        # 将LLM响应添加到消息历史
        assistant_msg = {"role": "assistant", "content": content}
        if tool_calls:  # 只有在有tool_calls时才添加该字段
            assistant_msg["tool_calls"] = tool_calls
        state.messages.append(assistant_msg)

    async def _handle_llm_completed(self, event: EventEnvelope) -> None:
        """处理LLM调用完成，决定下一步动作"""
        if not event.turn_id:
            return
        state = self.state_store.get_turn(event.session_id, event.turn_id)
        if not state:
            return

        # 从最后一条assistant消息中获取信息
        last_msg = None
        for msg in reversed(state.messages):
            if msg.get("role") == "assistant":
                last_msg = msg
                break

        if not last_msg:
            logger.warning("No assistant message found after LLM_CALL_COMPLETED")
            return

        content = last_msg.get("content", "")
        tool_calls = last_msg.get("tool_calls", [])

        # 如果有工具调用，触发工具执行
        if tool_calls:
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

        # 没有工具调用，结束本轮对话
        state.final_response = content
        await self.repo.complete_turn(event.turn_id, agent_response=content)

        # 保存本轮对话到历史
        self.state_store.append_to_history(event.session_id, state.messages)

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
