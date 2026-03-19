from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agentos.platform.config.config import config
from agentos.kernel.events.bus import PrivateEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import (
    ERROR_RAISED,
    LLM_CALL_COMPLETED,
    LLM_CALL_REQUESTED,
    LLM_CALL_RESULT,
    LLM_CALL_STARTED,
)
from agentos.kernel.runtime.workers.base import SessionWorker

if TYPE_CHECKING:
    from agentos.kernel.runtime.llm_runtime import LLMRuntime

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
        # model/provider 可能由事件直接指定（已是 model_id），也可能需要从 model key 解析
        raw_model = event.payload.get("model")
        raw_provider = event.payload.get("provider")
        if raw_provider and raw_model:
            # 事件已显式指定 provider 和 model_id，直接使用
            provider_name, model = raw_provider, raw_model
        else:
            # 通过 model key 解析
            model_key = raw_model or config.get("llm.default_model", "mock")
            provider_name, model = config.resolve_model(model_key)
        messages = event.payload.get("messages", [])
        tools = event.payload.get("tools")
        temperature = float(event.payload.get("temperature", config.get("agent.temperature", 0.2)))
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
                        "response": {
                            "content": resp.get("content", ""),
                            "tool_calls": resp.get("tool_calls", []),
                            **({"reasoning_details": resp["reasoning_details"]} if resp.get("reasoning_details") else {}),
                            **({"provider_specific_fields": resp["provider_specific_fields"]} if resp.get("provider_specific_fields") else {}),
                        },
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
            error_message = str(exc).strip() or type(exc).__name__
            await self.bus.publish(
                EventEnvelope(
                    type=ERROR_RAISED,
                    session_id=event.session_id,
                    turn_id=event.turn_id,
                    trace_id=llm_call_id,
                    source="llm",
                    payload={
                        "error_type": type(exc).__name__,
                        "error_message": error_message,
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
                        "response": {"content": f"LLM调用失败: {error_message}", "tool_calls": []},
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
