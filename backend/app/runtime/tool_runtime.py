from __future__ import annotations

import asyncio
import contextlib
import logging

from app.core.config import config
from app.events.envelope import EventEnvelope
from app.events.types import (
    ERROR_RAISED,
    TOOL_CALL_COMPLETED,
    TOOL_CALL_REQUESTED,
    TOOL_CALL_STARTED,
    TOOL_EXECUTION_END,
    TOOL_EXECUTION_START,
)
from app.runtime.publisher import EventPublisher
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolRuntime:
    def __init__(self, publisher: EventPublisher, registry: ToolRegistry):
        self.publisher = publisher
        self.registry = registry
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
            if event.type != TOOL_CALL_REQUESTED:
                continue
            asyncio.create_task(self._handle_tool_requested(event))

    async def _handle_tool_requested(self, event: EventEnvelope) -> None:
        tool_call_id = event.payload.get("tool_call_id")
        tool_name = event.payload.get("tool_name")
        arguments = event.payload.get("arguments", {})

        await self.publisher.publish(
            EventEnvelope(
                type=TOOL_CALL_STARTED,
                session_id=event.session_id,
                turn_id=event.turn_id,
                trace_id=tool_call_id,
                source="tool",
                payload={"tool_call_id": tool_call_id, "tool_name": tool_name},
            )
        )

        tool = self.registry.get(str(tool_name))
        if not tool:
            await self.publisher.publish(
                EventEnvelope(
                    type=TOOL_CALL_COMPLETED,
                    session_id=event.session_id,
                    turn_id=event.turn_id,
                    trace_id=tool_call_id,
                    source="tool",
                    payload={
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "result": None,
                        "success": False,
                        "error": f"tool not found: {tool_name}",
                    },
                )
            )
            return

        await self.publisher.publish(
            EventEnvelope(
                type=TOOL_EXECUTION_START,
                session_id=event.session_id,
                turn_id=event.turn_id,
                trace_id=tool_call_id,
                source="tool",
                payload={"tool_call_id": tool_call_id, "tool_name": tool_name},
            )
        )

        timeout = float(config.get(f"tools.{tool_name}.timeout", 15))
        if timeout <= 0:
            timeout = 15

        success = True
        error = ""
        result = None
        try:
            result = await asyncio.wait_for(tool.execute(**arguments), timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            success = False
            error = str(exc)
            logger.exception("tool execution failed")
            await self.publisher.publish(
                EventEnvelope(
                    type=ERROR_RAISED,
                    session_id=event.session_id,
                    turn_id=event.turn_id,
                    trace_id=tool_call_id,
                    source="tool",
                    payload={
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                        "context": {"tool_name": tool_name, "arguments": arguments},
                    },
                )
            )

        await self.publisher.publish(
            EventEnvelope(
                type=TOOL_EXECUTION_END,
                session_id=event.session_id,
                turn_id=event.turn_id,
                trace_id=tool_call_id,
                source="tool",
                payload={"tool_call_id": tool_call_id, "tool_name": tool_name, "success": success},
            )
        )

        await self.publisher.publish(
            EventEnvelope(
                type=TOOL_CALL_COMPLETED,
                session_id=event.session_id,
                turn_id=event.turn_id,
                trace_id=tool_call_id,
                source="tool",
                payload={
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "result": result,
                    "success": success,
                    "error": error,
                },
            )
        )
