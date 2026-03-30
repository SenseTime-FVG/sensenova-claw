from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any

from sensenova_claw.capabilities.tools.registry import _is_tool_config_enabled
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
    TOOL_CONFIRMATION_RESOLVED,
    USER_QUESTION_ASKED,
    USER_QUESTION_ANSWERED,
    USER_TURN_CANCEL_REQUESTED,
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
        # ── 任务生命周期管理 ──────────────────────────────
        # 所有活跃的工具执行 Task（与 LLMSessionWorker 对齐）
        self._active_tasks: set[asyncio.Task[None]] = set()
        # 按 turn_id 分组的 Task 集合，用于按 turn 精确取消
        self._turn_tasks: dict[str, set[asyncio.Task[None]]] = {}
        # 挂起中的确认请求：tool_call_id → asyncio.Event
        self._pending_confirmations: dict[str, asyncio.Event] = {}
        # 确认结果缓存：tool_call_id → bool
        self._confirmation_results: dict[str, bool] = {}
        # 已完成裁决的确认：tool_call_id
        self._resolved_confirmations: set[str] = set()
        # ask_user：question_id → asyncio.Future
        self._pending_questions: dict[str, asyncio.Future] = {}

    async def _handle(self, event: EventEnvelope) -> None:
        if event.type == TOOL_CALL_REQUESTED:
            self._start_tool_task(event)
        elif event.type == TOOL_CONFIRMATION_RESPONSE:
            await self._handle_confirmation_response(event)
        elif event.type == USER_QUESTION_ANSWERED:
            self._resolve_question(event)
        elif event.type == USER_TURN_CANCEL_REQUESTED:
            self._cancel_turn_tasks(event)

    # ── 任务生命周期管理 ──────────────────────────────

    def _start_tool_task(self, event: EventEnvelope) -> None:
        """创建工具执行 Task 并注册到跟踪集合"""
        task = asyncio.create_task(self._run_tool_task(event))
        self._active_tasks.add(task)
        if event.turn_id:
            self._turn_tasks.setdefault(event.turn_id, set()).add(task)
        task.add_done_callback(
            lambda done_task, turn_id=event.turn_id: self._cleanup_task(turn_id, done_task)
        )

    async def _run_tool_task(self, event: EventEnvelope) -> None:
        """工具执行 Task 包装器：捕获 CancelledError 并记录日志"""
        try:
            await self._handle_tool_requested(event)
        except asyncio.CancelledError:
            logger.info(
                "cancel tool request task session=%s turn=%s tool_call_id=%s",
                event.session_id,
                event.turn_id,
                event.payload.get("tool_call_id"),
            )
        except Exception:
            logger.exception(
                "tool request task crashed session=%s turn=%s tool_call_id=%s",
                event.session_id,
                event.turn_id,
                event.payload.get("tool_call_id"),
            )

    def _cleanup_task(self, turn_id: str | None, task: asyncio.Task[None]) -> None:
        """Task 完成后的清理回调"""
        self._active_tasks.discard(task)
        if not turn_id:
            return
        tasks = self._turn_tasks.get(turn_id)
        if not tasks:
            return
        tasks.discard(task)
        if not tasks:
            self._turn_tasks.pop(turn_id, None)

    def _resolve_turn_id(self, event: EventEnvelope) -> str | None:
        """解析 turn_id：优先取事件自身携带的，否则查 state_store 最新 turn"""
        if event.turn_id:
            return event.turn_id
        state_store = getattr(self.rt, "state_store", None)
        if state_store is None:
            return None
        latest_turn = state_store.latest_turn(event.session_id)
        return latest_turn.turn_id if latest_turn else None

    def _cancel_turn_tasks(self, event: EventEnvelope) -> None:
        """响应 USER_TURN_CANCEL_REQUESTED：按 turn_id 取消该 turn 的所有工具 Task"""
        turn_id = self._resolve_turn_id(event)
        if not turn_id:
            return
        tasks = list(self._turn_tasks.get(turn_id, ()))
        if not tasks:
            return
        logger.info(
            "cancel active tool tasks session=%s turn=%s count=%s",
            event.session_id,
            turn_id,
            len(tasks),
        )
        for task in tasks:
            task.cancel()

    def _is_turn_cancelled(self, event: EventEnvelope) -> bool:
        if not event.turn_id:
            return False
        state_store = getattr(self.rt, "state_store", None)
        if state_store is None:
            return False
        return state_store.is_turn_cancelled(event.session_id, event.turn_id)

    def _truncate_result(self, result: Any, tool_call_id: str, agent_id: str | None = None) -> Any:
        """Token 截断：统一控制传给 LLM 的结果长度"""
        result_str = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

        max_tokens = int(config.get("tools.result_truncation.max_tokens", 8000))
        max_chars = max_tokens * 3  # 粗略估算：1 token ≈ 3 字符

        if len(result_str) <= max_chars:
            return result

        save_dir = config.get("tools.result_truncation.save_dir", "workspace")
        from sensenova_claw.platform.config.workspace import (
            resolve_sensenova_claw_home,
            resolve_session_artifact_dir,
        )
        home = resolve_sensenova_claw_home(config)
        if save_dir == "workspace":
            session_dir = resolve_session_artifact_dir(home, self.session_id, agent_id=agent_id)
        else:
            session_dir = resolve_session_artifact_dir(save_dir, self.session_id, agent_id=agent_id)
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

    def _is_tool_enabled_for_agent(self, agent_id: str, tool_name: str) -> bool:
        """根据 config.yml 中的 enabled 开关判断工具是否启用。"""
        return _is_tool_config_enabled(tool_name)

    async def _publish_confirmation_resolved(
        self,
        event: EventEnvelope,
        *,
        tool_name: str,
        tool_call_id: str,
        approved: bool,
        reason: str,
        resolved_by: str,
    ) -> None:
        """发布审批已完成裁决事件。"""
        if tool_call_id in self._resolved_confirmations:
            return

        self._resolved_confirmations.add(tool_call_id)
        await self.bus.publish(
            EventEnvelope(
                type=TOOL_CONFIRMATION_RESOLVED,
                session_id=event.session_id,
                turn_id=event.turn_id,
                trace_id=tool_call_id,
                source="tool",
                payload={
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "approved": approved,
                    "status": "approved" if approved else "rejected",
                    "reason": reason,
                    "resolved_by": resolved_by,
                    "resolved_at_ms": int(time.time() * 1000),
                },
            )
        )

    async def _request_confirmation(self, event: EventEnvelope, tool: Tool) -> bool:
        """发布确认请求并挂起等待，根据 timeout_action 决定超时行为。

        timeout_action 取值：
        - "reject"（默认）: 超时自动拒绝
        - "approve": 超时自动批准
        - "block": 无限等待直到用户响应
        """
        tool_call_id = event.payload["tool_call_id"]
        wait_event = asyncio.Event()
        self._pending_confirmations[tool_call_id] = wait_event
        timeout = float(config.get("tools.permission.confirmation_timeout", 60))
        timeout_action = str(config.get("tools.permission.timeout_action", "reject")).lower()

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
                    "timeout": timeout,
                    "timeout_action": timeout_action,
                    "requested_at_ms": int(time.time() * 1000),
                    "message": f"工具 {tool.name} (风险等级: {tool.risk_level.value}) 请求执行，是否允许？",
                },
            )
        )

        try:
            if timeout_action == "block":
                # 无限等待，直到用户响应或 worker 停止
                await wait_event.wait()
            else:
                await asyncio.wait_for(wait_event.wait(), timeout=timeout)
            if tool_call_id not in self._confirmation_results:
                return False
            approved = self._confirmation_results.pop(tool_call_id)
            await self._publish_confirmation_resolved(
                event,
                tool_name=tool.name,
                tool_call_id=tool_call_id,
                approved=approved,
                reason="user_approved" if approved else "user_rejected",
                resolved_by="user",
            )
            return approved
        except asyncio.TimeoutError:
            if timeout_action == "approve":
                logger.warning("工具确认超时，自动批准: tool_call_id=%s", tool_call_id)
                await self._publish_confirmation_resolved(
                    event,
                    tool_name=tool.name,
                    tool_call_id=tool_call_id,
                    approved=True,
                    reason="timeout_approved",
                    resolved_by="timeout",
                )
                return True
            else:
                logger.warning("工具确认超时，自动拒绝: tool_call_id=%s", tool_call_id)
                await self._publish_confirmation_resolved(
                    event,
                    tool_name=tool.name,
                    tool_call_id=tool_call_id,
                    approved=False,
                    reason="timeout_rejected",
                    resolved_by="timeout",
                )
                return False
        finally:
            self._pending_confirmations.pop(tool_call_id, None)
            self._confirmation_results.pop(tool_call_id, None)

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
        """停止时取消所有运行中的工具 Task、挂起的问题和确认等待"""
        # ① 取消所有活跃的工具执行 Task
        for task in list(self._active_tasks):
            task.cancel()
        # ② 唤醒 block 模式下挂起的确认等待
        for wait_event in self._pending_confirmations.values():
            wait_event.set()
        self._pending_confirmations.clear()
        self._confirmation_results.clear()
        self._resolved_confirmations.clear()
        for future in self._pending_questions.values():
            if not future.done():
                future.cancel()
        self._pending_questions.clear()
        # ③ 停止 worker 主循环
        await super().stop()
        # ④ 等待所有工具 Task 完成（它们已被 cancel，这里确保清理完毕）
        for task in list(self._active_tasks):
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._active_tasks.clear()
        self._turn_tasks.clear()

    async def _handle_confirmation_response(self, event: EventEnvelope) -> None:
        """处理用户确认响应，唤醒挂起的任务"""
        tool_call_id = event.payload.get("tool_call_id")
        approved = event.payload.get("approved", False)

        if tool_call_id in self._resolved_confirmations:
            logger.debug("ignore late tool confirmation response: tool_call_id=%s", tool_call_id)
            return

        self._confirmation_results[tool_call_id] = approved
        wait_event = self._pending_confirmations.get(tool_call_id)
        if wait_event:
            wait_event.set()  # 唤醒挂起的 _request_confirmation
            return
        self._confirmation_results.pop(tool_call_id, None)
        logger.debug("ignore tool confirmation response without pending request: tool_call_id=%s", tool_call_id)

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
        source_agent_id = str(event.payload.get("_source_agent_id") or event.agent_id or "").strip() or "default"

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

        if not self._is_tool_enabled_for_agent(source_agent_id, str(tool_name)):
            await self._publish_tool_result(
                event,
                result=f"工具已被当前 Agent 禁用: {tool_name}",
                success=False,
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
        exec_kwargs["_source_agent_id"] = source_agent_id
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
            result = self._truncate_result(result, tool_call_id, agent_id=source_agent_id)
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
