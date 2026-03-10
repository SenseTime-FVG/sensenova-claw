from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from app.core.config import config
from app.events.envelope import EventEnvelope
from app.events.types import (
    AGENT_STEP_COMPLETED,
    AGENT_STEP_STARTED,
    LLM_CALL_COMPLETED,
    LLM_CALL_REQUESTED,
    LLM_CALL_RESULT,
    TOOL_CALL_REQUESTED,
    TOOL_CALL_RESULT,
    USER_INPUT,
)
from app.events.bus import PrivateEventBus
from app.runtime.state import TurnState
from app.runtime.workers.base import SessionWorker

if TYPE_CHECKING:
    from app.runtime.agent_runtime import AgentRuntime

logger = logging.getLogger(__name__)


class AgentSessionWorker(SessionWorker):
    """Agent 会话级 Worker：编排对话流程"""

    def __init__(self, session_id: str, private_bus: PrivateEventBus, runtime: AgentRuntime):
        super().__init__(session_id, private_bus)
        self.rt = runtime

    async def _handle(self, event: EventEnvelope) -> None:
        if event.type == USER_INPUT:
            await self._handle_user_input(event)
        elif event.type == LLM_CALL_RESULT:
            await self._handle_llm_result(event)
        elif event.type == LLM_CALL_COMPLETED:
            await self._handle_llm_completed(event)
        elif event.type == TOOL_CALL_RESULT:
            await self._handle_tool_result(event)

    async def _handle_user_input(self, event: EventEnvelope) -> None:
        content = str(event.payload.get("content", ""))
        turn_id = event.turn_id or f"turn_{uuid.uuid4().hex[:12]}"

        await self.rt.repo.create_session(self.session_id, meta={"title": content[:20] or "新会话"})
        await self.rt.repo.update_session_activity(self.session_id)
        await self.rt.repo.create_turn(turn_id=turn_id, session_id=self.session_id, user_input=content)

        # 获取历史消息
        history = self.rt.state_store.get_session_history(self.session_id)
        messages = self.rt.context_builder.build_messages(content, history)
        state = TurnState(turn_id=turn_id, user_input=content, messages=messages)
        self.rt.state_store.set_turn(self.session_id, state)

        await self.bus.publish(
            EventEnvelope(
                type=AGENT_STEP_STARTED,
                session_id=self.session_id,
                turn_id=turn_id,
                source="agent",
                payload={"step_type": "llm_call", "description": "开始处理用户输入"},
            )
        )

        llm_call_id = f"llm_{uuid.uuid4().hex[:12]}"
        await self.bus.publish(
            EventEnvelope(
                type=LLM_CALL_REQUESTED,
                session_id=self.session_id,
                turn_id=turn_id,
                trace_id=llm_call_id,
                source="agent",
                payload={
                    "llm_call_id": llm_call_id,
                    "provider": config.get("agent.provider", "mock"),
                    "model": config.get("agent.default_model"),
                    "messages": messages,
                    "tools": self.rt.tool_registry.as_llm_tools(),
                    "temperature": config.get("agent.default_temperature", 0.2),
                },
            )
        )

    async def _handle_llm_result(self, event: EventEnvelope) -> None:
        """处理 LLM 返回的结果"""
        if not event.turn_id:
            return
        state = self.rt.state_store.get_turn(event.session_id, event.turn_id)
        if not state:
            return

        response = event.payload.get("response", {})
        content = response.get("content", "")
        tool_calls = response.get("tool_calls", [])

        # 将 LLM 响应添加到消息历史
        assistant_msg = {"role": "assistant", "content": content}
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        state.messages.append(assistant_msg)

    async def _handle_llm_completed(self, event: EventEnvelope) -> None:
        """处理 LLM 调用完成，决定下一步动作"""
        if not event.turn_id:
            return
        state = self.rt.state_store.get_turn(event.session_id, event.turn_id)
        if not state:
            return

        # 从最后一条 assistant 消息中获取信息
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
                await self.bus.publish(
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
        await self.rt.repo.complete_turn(event.turn_id, agent_response=content)

        # 保存本轮对话到历史
        self.rt.state_store.append_to_history(event.session_id, state.messages)

        await self.bus.publish(
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

    async def _handle_tool_result(self, event: EventEnvelope) -> None:
        """处理工具返回结果，收集结果并在所有工具完成后触发下一轮 LLM 调用"""
        if not event.turn_id:
            return
        state = self.rt.state_store.get_turn(event.session_id, event.turn_id)
        if not state:
            return

        tool_call_id = event.payload.get("tool_call_id")
        if tool_call_id in state.pending_tool_calls:
            state.pending_tool_calls.remove(tool_call_id)

        tool_name = str(event.payload.get("tool_name"))
        result = event.payload.get("result")
        state.tool_results.append({"tool_name": tool_name, "result": result})
        state.messages = self.rt.context_builder.append_tool_result(
            state.messages,
            tool_name=tool_name,
            result=result,
            tool_call_id=str(tool_call_id) if tool_call_id else None,
        )

        if state.pending_tool_calls:
            return

        llm_call_id = f"llm_{uuid.uuid4().hex[:12]}"
        await self.bus.publish(
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
                    "tools": self.rt.tool_registry.as_llm_tools(),
                    "temperature": config.get("agent.default_temperature", 0.2),
                },
            )
        )
