from __future__ import annotations

import asyncio
import contextlib
import logging

from app.core.config import config
from app.events.envelope import EventEnvelope
from app.events.types import ERROR_RAISED, LLM_CALL_COMPLETED, LLM_CALL_REQUESTED, LLM_CALL_RESULT, LLM_CALL_STARTED
from app.llm.factory import LLMFactory
from app.runtime.publisher import EventPublisher

logger = logging.getLogger(__name__)


class LLMRuntime:
    def __init__(self, publisher: EventPublisher, factory: LLMFactory):
        self.publisher = publisher
        self.factory = factory
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
            if event.type != LLM_CALL_REQUESTED:
                continue
            await self._handle_llm_requested(event)

    async def _handle_llm_requested(self, event: EventEnvelope) -> None:
        llm_call_id = event.payload.get("llm_call_id")
        model = event.payload.get("model") or config.get("agent.default_model")
        provider_name = event.payload.get("provider") or config.get("agent.provider", "mock")
        messages = event.payload.get("messages", [])
        tools = event.payload.get("tools")
        temperature = float(event.payload.get("temperature", config.get("agent.default_temperature", 0.2)))
        max_tokens = event.payload.get("max_tokens")

        logger.debug("LLM call input | provider=%s model=%s llm_call_id=%s messages=%s tools=%s", provider_name, model, llm_call_id, messages, tools)

        await self.publisher.publish(
            EventEnvelope(
                type=LLM_CALL_STARTED,
                session_id=event.session_id,
                turn_id=event.turn_id,
                trace_id=llm_call_id,
                source="llm",
                payload={"llm_call_id": llm_call_id, "model": model},
            )
        )

        provider = self.factory.get_provider(provider_name)
        try:
            resp = await provider.call(
                model=model,
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            # 先发送结果事件
            await self.publisher.publish(
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
            # 再发送完成事件
            await self.publisher.publish(
                EventEnvelope(
                    type=LLM_CALL_COMPLETED,
                    session_id=event.session_id,
                    turn_id=event.turn_id,
                    trace_id=llm_call_id,
                    source="llm",
                    payload={
                        "llm_call_id": llm_call_id,
                    },
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("llm call failed")
            await self.publisher.publish(
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
            # 错误时也发送结果事件
            await self.publisher.publish(
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
            await self.publisher.publish(
                EventEnvelope(
                    type=LLM_CALL_COMPLETED,
                    session_id=event.session_id,
                    turn_id=event.turn_id,
                    trace_id=llm_call_id,
                    source="llm",
                    payload={
                        "llm_call_id": llm_call_id,
                    },
                )
            )
