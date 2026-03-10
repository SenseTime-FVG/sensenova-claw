from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.config import config
from app.events.bus import PrivateEventBus
from app.events.envelope import EventEnvelope
from app.events.types import (
    ERROR_RAISED,
    TOOL_CALL_COMPLETED,
    TOOL_CALL_REQUESTED,
    TOOL_CALL_RESULT,
    TOOL_CALL_STARTED,
)
from app.runtime.workers.base import SessionWorker

if TYPE_CHECKING:
    from app.runtime.tool_runtime import ToolRuntime

logger = logging.getLogger(__name__)


class ToolSessionWorker(SessionWorker):
    """Tool 会话级 Worker：执行工具调用"""

    def __init__(self, session_id: str, private_bus: PrivateEventBus, runtime: ToolRuntime):
        super().__init__(session_id, private_bus)
        self.rt = runtime

    async def _handle(self, event: EventEnvelope) -> None:
        if event.type == TOOL_CALL_REQUESTED:
            # 保留并发执行：每个工具调用独立 task
            asyncio.create_task(self._handle_tool_requested(event))

    def _truncate_result(self, result: any, tool_call_id: str) -> any:
        """截断超长工具结果，保存完整内容到文件"""
        result_str = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

        max_chars = 16000 * 3

        if len(result_str) <= max_chars:
            return result

        workspace_dir = Path(config.get("system.workspace_dir", "./SenseAssistant/workspace"))
        session_dir = workspace_dir / self.session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        file_name = f"tool_result_{tool_call_id[:8]}_{uuid.uuid4().hex[:6]}.txt"
        file_path = session_dir / file_name
        file_path.write_text(result_str, encoding="utf-8")

        truncated = result_str[:max_chars]
        truncated += f"\n\n工具内容超长，以上是截断内容，全文内容保存在 {file_path}"

        return truncated

    async def _handle_tool_requested(self, event: EventEnvelope) -> None:
        tool_call_id = event.payload.get("tool_call_id")
        tool_name = event.payload.get("tool_name")
        arguments = event.payload.get("arguments", {})

        if not tool_call_id:
            logger.error("Missing tool_call_id in event: %s", event)
            return

        await self.bus.publish(
            EventEnvelope(
                type=TOOL_CALL_STARTED,
                session_id=event.session_id,
                turn_id=event.turn_id,
                trace_id=tool_call_id,
                source="tool",
                payload={"tool_call_id": tool_call_id, "tool_name": tool_name},
            )
        )

        tool = self.rt.registry.get(str(tool_name))
        if not tool:
            await self.bus.publish(
                EventEnvelope(
                    type=TOOL_CALL_RESULT,
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
            await self.bus.publish(
                EventEnvelope(
                    type=TOOL_CALL_COMPLETED,
                    session_id=event.session_id,
                    turn_id=event.turn_id,
                    trace_id=tool_call_id,
                    source="tool",
                    payload={
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "success": False,
                    },
                )
            )
            return

        timeout = float(config.get(f"tools.{tool_name}.timeout", 15))
        if timeout <= 0:
            timeout = 15

        success = True
        error = ""
        result = None
        try:
            result = await asyncio.wait_for(tool.execute(**arguments), timeout=timeout)
            result = self._truncate_result(result, tool_call_id)
        except Exception as exc:  # noqa: BLE001
            success = False
            error = str(exc)
            result = f"工具执行失败: {error}"
            logger.exception("tool execution failed")
            await self.bus.publish(
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

        # 发布 tool.call_result（携带执行结果）
        await self.bus.publish(
            EventEnvelope(
                type=TOOL_CALL_RESULT,
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

        # 发布 tool.call_completed（终止信号 + 摘要，不携带 result 内容）
        await self.bus.publish(
            EventEnvelope(
                type=TOOL_CALL_COMPLETED,
                session_id=event.session_id,
                turn_id=event.turn_id,
                trace_id=tool_call_id,
                source="tool",
                payload={
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "success": success,
                },
            )
        )
