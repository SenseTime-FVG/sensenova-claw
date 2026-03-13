from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from agentos.platform.config.config import config
from agentos.kernel.events.bus import PrivateEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import (
    ERROR_RAISED,
    TOOL_CALL_COMPLETED,
    TOOL_CALL_REQUESTED,
    TOOL_CALL_RESULT,
    TOOL_CALL_STARTED,
    TOOL_CONFIRMATION_REQUESTED,
    TOOL_CONFIRMATION_RESPONSE,
)
from agentos.capabilities.tools.base import Tool
from agentos.kernel.runtime.workers.base import SessionWorker

if TYPE_CHECKING:
    from agentos.kernel.runtime.tool_runtime import ToolRuntime

logger = logging.getLogger(__name__)


class ToolSessionWorker(SessionWorker):
    """Tool 会话级 Worker：执行工具调用"""

    def __init__(self, session_id: str, private_bus: PrivateEventBus, runtime: ToolRuntime):
        super().__init__(session_id, private_bus)
        self.rt = runtime
        # 挂起中的确认请求：tool_call_id → asyncio.Event
        self._pending_confirmations: dict[str, asyncio.Event] = {}
        # 确认结果缓存：tool_call_id → bool
        self._confirmation_results: dict[str, bool] = {}

    async def _handle(self, event: EventEnvelope) -> None:
        if event.type == TOOL_CALL_REQUESTED:
            # 保留并发执行：每个工具调用独立 task
            asyncio.create_task(self._handle_tool_requested(event))
        elif event.type == TOOL_CONFIRMATION_RESPONSE:
            await self._handle_confirmation_response(event)

    def _truncate_result(self, result: any, tool_call_id: str) -> any:
        """Token 截断：统一控制传给 LLM 的结果长度"""
        result_str = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

        max_tokens = int(config.get("tools.result_truncation.max_tokens", 8000))
        max_chars = max_tokens * 3  # 粗略估算：1 token ≈ 3 字符

        if len(result_str) <= max_chars:
            return result

        save_dir = config.get("tools.result_truncation.save_dir", "workspace")
        workspace_dir = Path(config.get("system.workspace_dir", "./SenseAssistant/workspace"))
        if save_dir == "workspace":
            base_dir = workspace_dir
        else:
            base_dir = Path(save_dir)
        session_dir = base_dir / self.session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        file_name = f"tool_result_{tool_call_id[:8]}_{uuid.uuid4().hex[:6]}.txt"
        file_path = session_dir / file_name
        file_path.write_text(result_str, encoding="utf-8")

        truncated = result_str[:max_chars]
        truncated += f"\n\n[内容已截断] 完整结果已保存到: {file_path}"

        return truncated

    def _needs_confirmation(self, tool: Tool) -> bool:
        """判断工具是否需要用户确认"""
        if not config.get("tools.permission.enabled", False):
            return False
        auto_levels = config.get("tools.permission.auto_approve_levels", ["low"])
        return tool.risk_level.value not in auto_levels

    async def _request_confirmation(self, event: EventEnvelope, tool: Tool) -> bool:
        """发布确认请求并挂起等待，超时自动拒绝"""
        tool_call_id = event.payload["tool_call_id"]
        wait_event = asyncio.Event()
        self._pending_confirmations[tool_call_id] = wait_event

        # 发布确认请求事件
        await self.bus.publish(
            EventEnvelope(
                type=TOOL_CONFIRMATION_REQUESTED,
                session_id=event.session_id,
                turn_id=event.turn_id,
                trace_id=tool_call_id,
                source="tool",
                payload={
                    "tool_call_id": tool_call_id,
                    "tool_name": tool.name,
                    "arguments": event.payload.get("arguments", {}),
                    "risk_level": tool.risk_level.value,
                    "message": f"工具 {tool.name} (风险等级: {tool.risk_level.value}) 请求执行，是否允许？",
                },
            )
        )

        # 挂起等待，超时自动拒绝
        timeout = float(config.get("tools.permission.confirmation_timeout", 60))
        try:
            await asyncio.wait_for(wait_event.wait(), timeout=timeout)
            return self._confirmation_results.pop(tool_call_id, False)
        except asyncio.TimeoutError:
            logger.warning("工具确认超时，自动拒绝: tool_call_id=%s", tool_call_id)
            return False
        finally:
            self._pending_confirmations.pop(tool_call_id, None)

    async def _handle_confirmation_response(self, event: EventEnvelope) -> None:
        """处理用户确认响应，唤醒挂起的任务"""
        tool_call_id = event.payload.get("tool_call_id")
        approved = event.payload.get("approved", False)

        self._confirmation_results[tool_call_id] = approved
        wait_event = self._pending_confirmations.get(tool_call_id)
        if wait_event:
            wait_event.set()  # 唤醒挂起的 _request_confirmation

    async def _publish_tool_result(self, event: EventEnvelope, result: str, success: bool) -> None:
        """发布工具拒绝/失败结果"""
        tool_call_id = event.payload.get("tool_call_id")
        tool_name = event.payload.get("tool_name")
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
                    "error": "" if success else result,
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
                    "success": success,
                },
            )
        )

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

        # 权限确认：高风险工具需要用户确认
        if self._needs_confirmation(tool):
            approved = await self._request_confirmation(event, tool)
            if not approved:
                await self._publish_tool_result(event, result="用户拒绝执行该工具", success=False)
                return

        timeout = float(config.get(f"tools.{tool_name}.timeout", 15))
        if timeout <= 0:
            timeout = 15

        success = True
        error = ""
        result = None
        # 构建执行参数：注入内部上下文对象（不可 JSON 序列化，仅供工具内部使用）
        exec_kwargs = dict(arguments)
        if self.rt.path_policy:
            exec_kwargs["_path_policy"] = self.rt.path_policy
        if self.rt.agent_registry:
            exec_kwargs["_agent_registry"] = self.rt.agent_registry

        try:
            result = await asyncio.wait_for(
                tool.execute(**exec_kwargs, _session_id=event.session_id),
                timeout=timeout,
            )
            result = self._truncate_result(result, tool_call_id)
        except Exception as exc:  # noqa: BLE001
            success = False
            error = str(exc) or f"{type(exc).__name__}"
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
