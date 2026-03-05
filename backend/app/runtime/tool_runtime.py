from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from pathlib import Path

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

    def _truncate_result(self, result: any, session_id: str, tool_call_id: str) -> any:
        """截断超长工具结果，保存完整内容到文件"""
        result_str = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

        # 粗略估算：1 token ≈ 4 字符（中文）或 1 字符（英文），取平均 2.5
        max_chars = 16000 * 3

        if len(result_str) <= max_chars:
            return result

        # 保存完整内容到文件
        workspace_dir = Path(config.get("system.workspace_dir", "./SenseAssistant/workspace"))
        session_dir = workspace_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        file_name = f"tool_result_{tool_call_id[:8]}_{uuid.uuid4().hex[:6]}.txt"
        file_path = session_dir / file_name
        file_path.write_text(result_str, encoding="utf-8")

        # 截断内容
        truncated = result_str[:max_chars]
        truncated += f"\n\n工具内容超长，以上是截断内容，全文内容保存在 {file_path}"

        return truncated

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
            # 截断超长结果
            result = self._truncate_result(result, event.session_id, tool_call_id)
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
