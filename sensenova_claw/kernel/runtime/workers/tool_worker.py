from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sensenova_claw.platform.config.config import config
from sensenova_claw.kernel.events.bus import PrivateEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import (
    ERROR_RAISED,
    TOOL_CALL_COMPLETED,
    TOOL_CALL_REQUESTED,
    TOOL_CALL_RESULT,
    TOOL_CALL_STARTED,
    TOOL_CONFIRMATION_REQUESTED,
    TOOL_CONFIRMATION_RESPONSE,
    USER_QUESTION_ASKED,
    USER_QUESTION_ANSWERED,
)
from sensenova_claw.capabilities.tools.base import Tool
from sensenova_claw.kernel.runtime.workers.base import SessionWorker

if TYPE_CHECKING:
    from sensenova_claw.kernel.runtime.tool_runtime import ToolRuntime

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
        # ask_user：question_id → asyncio.Future
        self._pending_questions: dict[str, asyncio.Future] = {}

    async def _handle(self, event: EventEnvelope) -> None:
        if event.type == TOOL_CALL_REQUESTED:
            asyncio.create_task(self._handle_tool_requested(event))
        elif event.type == TOOL_CONFIRMATION_RESPONSE:
            await self._handle_confirmation_response(event)
        elif event.type == USER_QUESTION_ANSWERED:
            self._resolve_question(event)

    def _is_turn_cancelled(self, event: EventEnvelope) -> bool:
        if not event.turn_id:
            return False
        state_store = getattr(self.rt, "state_store", None)
        if state_store is None:
            return False
        return state_store.is_turn_cancelled(event.session_id, event.turn_id)

    def _truncate_result(self, result: Any, tool_call_id: str) -> Any:
        """Token 截断：统一控制传给 LLM 的结果长度"""
        result_str = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

        max_tokens = int(config.get("tools.result_truncation.max_tokens", 8000))
        max_chars = max_tokens * 3  # 粗略估算：1 token ≈ 3 字符

        if len(result_str) <= max_chars:
            return result

        save_dir = config.get("tools.result_truncation.save_dir", "workspace")
        from sensenova_claw.platform.config.workspace import resolve_sensenova_claw_home
        home = resolve_sensenova_claw_home(config)
        if save_dir == "workspace":
            base_dir = home
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

    # ── ask_user 支持 ──────────────────────────────────

    def _make_ask_user_handler(self):
        """创建注入到 AskUserTool 的回调函数，封装事件发布和等待逻辑"""
        worker = self

        async def handler(
            question: str, options: list | None, multi_select: bool,
            session_id: str, turn_id: str, tool_call_id: str,
            source_agent_id: str | None = None,
        ) -> dict:
            if worker._pending_questions:
                return {"success": False, "error": "已有待回答问题，请先回答当前问题"}

            question_id = f"q_{uuid.uuid4().hex[:8]}"
            future: asyncio.Future = asyncio.get_running_loop().create_future()
            worker._pending_questions[question_id] = future

            timeout = float(config.get("tools.ask_user.timeout", 300))
            resolved_source_agent_id = str(source_agent_id or "").strip() or "default"

            await worker.bus.publish(EventEnvelope(
                type=USER_QUESTION_ASKED,
                session_id=session_id, turn_id=turn_id, trace_id=tool_call_id,
                source="tool",
                payload={
                    "question_id": question_id, "question": question,
                    "options": options, "multi_select": multi_select, "timeout": timeout,
                    "source_agent_id": resolved_source_agent_id,
                },
            ))

            try:
                result = await asyncio.wait_for(future, timeout=timeout)
                return result
            except asyncio.TimeoutError:
                return {"success": False, "error": "用户未在规定时间内回答"}
            finally:
                worker._pending_questions.pop(question_id, None)

        return handler

    def _resolve_question(self, event: EventEnvelope) -> None:
        """处理用户回答，唤醒挂起的 Future"""
        question_id = event.payload.get("question_id")
        future = self._pending_questions.get(question_id)
        if future and not future.done():
            cancelled = event.payload.get("cancelled", False)
            if cancelled:
                future.set_result({"success": False, "error": "用户取消了回答"})
            else:
                future.set_result({"success": True, "answer": event.payload.get("answer", "")})

    async def stop(self) -> None:
        """停止时取消所有挂起的问题"""
        for future in self._pending_questions.values():
            if not future.done():
                future.cancel()
        self._pending_questions.clear()
        await super().stop()

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
        if self._is_turn_cancelled(event):
            logger.info(
                "skip tool request for cancelled turn session=%s turn=%s tool_call_id=%s",
                event.session_id,
                event.turn_id,
                tool_call_id,
            )
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

        if tool_name == "send_message":
            default_timeout = 600
        elif tool_name == "ask_user":
            default_timeout = 300
        else:
            default_timeout = 15
        timeout = float(config.get(f"tools.{tool_name}.timeout", default_timeout))
        if timeout <= 0:
            timeout = default_timeout

        success = True
        error = ""
        result = None
        # 构建执行参数：注入内部上下文对象（不可 JSON 序列化，仅供工具内部使用）
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except (json.JSONDecodeError, TypeError):
                arguments = {}
        exec_kwargs = dict(arguments) if isinstance(arguments, dict) else {}
        if self.rt.agent_registry:
            exec_kwargs["_agent_registry"] = self.rt.agent_registry
        agent_workdir = event.payload.get("_agent_workdir")
        if agent_workdir:
            exec_kwargs["_agent_workdir"] = agent_workdir
        exec_kwargs["_source_agent_id"] = (
            str(event.payload.get("_source_agent_id") or event.agent_id or "").strip() or "default"
        )
        if event.turn_id:
            exec_kwargs["_turn_id"] = event.turn_id
        if tool_call_id:
            exec_kwargs["_tool_call_id"] = tool_call_id
        # 注入 ask_user 回调（AskUserTool 内部调用）
        exec_kwargs["_ask_user_handler"] = self._make_ask_user_handler()
        # 注入公共事件总线（供 manage_todolist 等工具发布广播事件）
        exec_kwargs["_event_bus"] = self.bus._public_bus

        try:
            result = await asyncio.wait_for(
                tool.execute(**exec_kwargs, _session_id=event.session_id),
                timeout=timeout,
            )
            result = self._truncate_result(result, tool_call_id)
        except Exception as exc:  # noqa: BLE001
            success = False
            error = str(exc).strip() or type(exc).__name__
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
                        "error_message": error,
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
