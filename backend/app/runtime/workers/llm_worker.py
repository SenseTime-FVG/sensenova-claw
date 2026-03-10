from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.config import config
from app.events.bus import PrivateEventBus
from app.events.envelope import EventEnvelope
from app.events.types import (
    ERROR_RAISED,
    LLM_CALL_COMPLETED,
    LLM_CALL_REQUESTED,
    LLM_CALL_RESULT,
    LLM_CALL_STARTED,
)
from app.runtime.workers.base import SessionWorker

if TYPE_CHECKING:
    from app.runtime.llm_runtime import LLMRuntime

logger = logging.getLogger(__name__)


class LLMSessionWorker(SessionWorker):
    """LLM 会话级 Worker：处理 LLM 调用"""

    def __init__(self, session_id: str, private_bus: PrivateEventBus, runtime: LLMRuntime):
        super().__init__(session_id, private_bus)
        self.rt = runtime

    async def _handle(self, event: EventEnvelope) -> None:
        if event.type == LLM_CALL_REQUESTED:
            await self._handle_llm_requested(event)

    async def _handle_llm_requested(self, event: EventEnvelope) -> None:
        llm_call_id = event.payload.get("llm_call_id")
        model = event.payload.get("model") or config.get("agent.default_model")
        provider_name = event.payload.get("provider") or config.get("agent.provider", "mock")
        messages = event.payload.get("messages", [])
        tools = event.payload.get("tools")
        temperature = float(event.payload.get("temperature", config.get("agent.default_temperature", 0.2)))
        max_tokens = event.payload.get("max_tokens")

        logger.debug(
            "LLM call input | provider=%s model=%s llm_call_id=%s messages=%s tools=%s",
            provider_name, model, llm_call_id, messages, tools,
        )

        await self.bus.publish(
            EventEnvelope(
                type=LLM_CALL_STARTED,
                session_id=event.session_id,
                turn_id=event.turn_id,
                trace_id=llm_call_id,
                source="llm",
                payload={"llm_call_id": llm_call_id, "model": model},
            )
        )

        provider = self.rt.factory.get_provider(provider_name)
        try:
            resp = await provider.call(
                model=model,
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            await self.bus.publish(
                EventEnvelope(
                    type=LLM_CALL_RESULT,
                    session_id=event.session_id,
                    turn_id=event.turn_id,
                    trace_id=llm_call_id,
                    source="llm",
                    payload={
                        "llm_call_id": llm_call_id,
                        "response": {"content": resp.get("content", ""), "tool_calls": resp.get("tool_calls", [])},
                        "usage": resp.get("usage", {}),
                        "finish_reason": resp.get("finish_reason", "stop"),
                    },
                )
            )
            await self.bus.publish(
                EventEnvelope(
                    type=LLM_CALL_COMPLETED,
                    session_id=event.session_id,
                    turn_id=event.turn_id,
                    trace_id=llm_call_id,
                    source="llm",
                    payload={"llm_call_id": llm_call_id},
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("llm call failed")
            await self.bus.publish(
                EventEnvelope(
                    type=ERROR_RAISED,
                    session_id=event.session_id,
                    turn_id=event.turn_id,
                    trace_id=llm_call_id,
                    source="llm",
                    payload={
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                        "context": {"model": model, "provider": provider_name},
                    },
                )
            )
            await self.bus.publish(
                EventEnvelope(
                    type=LLM_CALL_RESULT,
                    session_id=event.session_id,
                    turn_id=event.turn_id,
                    trace_id=llm_call_id,
                    source="llm",
                    payload={
                        "llm_call_id": llm_call_id,
                        "response": {"content": f"LLM调用失败: {str(exc)}", "tool_calls": []},
                        "usage": {},
                        "finish_reason": "error",
                    },
                )
            )
            await self.bus.publish(
                EventEnvelope(
                    type=LLM_CALL_COMPLETED,
                    session_id=event.session_id,
                    turn_id=event.turn_id,
                    trace_id=llm_call_id,
                    source="llm",
                    payload={"llm_call_id": llm_call_id},
                )
            )
