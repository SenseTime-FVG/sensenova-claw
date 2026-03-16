from __future__ import annotations

import json
import logging
import uuid
from typing import Any, TYPE_CHECKING

from agentos.platform.config.config import config
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import (
    AGENT_MESSAGE_COMPLETED,
    AGENT_MESSAGE_FAILED,
    AGENT_STEP_COMPLETED,
    AGENT_STEP_STARTED,
    ERROR_RAISED,
    LLM_CALL_COMPLETED,
    LLM_CALL_REQUESTED,
    LLM_CALL_RESULT,
    TOOL_CALL_REQUESTED,
    TOOL_CALL_RESULT,
    USER_INPUT,
    USER_TURN_CANCEL_REQUESTED,
)
from agentos.kernel.events.bus import PrivateEventBus
from agentos.kernel.runtime.state import TurnState
from agentos.kernel.runtime.workers.base import SessionWorker

if TYPE_CHECKING:
    from agentos.capabilities.agents.config import AgentConfig
    from agentos.kernel.runtime.agent_runtime import AgentRuntime

logger = logging.getLogger(__name__)


class AgentSessionWorker(SessionWorker):
    """Agent 会话级 Worker：编排对话流程

    支持通过 agent_config 使用独立的 provider/model/tools/skills 配置。
    当 agent_config 为 None 时，回退到全局 config（向后兼容）。
    """

    MAX_CONSECUTIVE_ERRORS = 3

    def __init__(
        self,
        session_id: str,
        private_bus: PrivateEventBus,
        runtime: AgentRuntime,
        agent_config: AgentConfig | None = None,
    ):
        super().__init__(session_id, private_bus)
        self.rt = runtime
        self.agent_config = agent_config
        self._consecutive_errors = 0

    # ── 配置读取辅助 ──────────────────────────────────

    def _get_provider(self) -> str:
        if self.agent_config and self.agent_config.provider:
            return self.agent_config.provider
        return config.get("agent.provider", "mock")

    def _get_model(self) -> str:
        if self.agent_config and self.agent_config.model:
            return self.agent_config.model
        return config.get("agent.default_model")

    def _get_temperature(self) -> float:
        if self.agent_config:
            return self.agent_config.temperature
        return config.get("agent.default_temperature", 0.2)

    def _get_filtered_tools(self) -> list[dict]:
        """根据 Agent 配置过滤可用工具"""
        all_tools = self.rt.tool_registry.as_llm_tools()
        if not self.agent_config or not self.agent_config.tools:
            return all_tools  # 空列表 = 全部工具
        allowed = set(self.agent_config.tools)
        # 始终保留 send_message 工具
        always_keep = {"send_message"}
        return [t for t in all_tools if t["name"] in allowed or t["name"] in always_keep]

    # ── 事件处理 ──────────────────────────────────────

    async def _handle(self, event: EventEnvelope) -> None:
        try:
            if (
                event.turn_id
                and event.type not in {USER_INPUT, USER_TURN_CANCEL_REQUESTED}
                and self.rt.state_store.is_turn_cancelled(event.session_id, event.turn_id)
            ):
                logger.info(
                    "忽略已取消 turn 的事件 session=%s turn=%s type=%s",
                    event.session_id,
                    event.turn_id,
                    event.type,
                )
                return
            if event.type == USER_INPUT:
                await self._handle_user_input(event)
            elif event.type == USER_TURN_CANCEL_REQUESTED:
                await self._handle_turn_cancel_requested(event)
            elif event.type == AGENT_MESSAGE_COMPLETED:
                await self._handle_agent_message_completed(event)
            elif event.type == AGENT_MESSAGE_FAILED:
                await self._handle_agent_message_failed(event)
            elif event.type == LLM_CALL_RESULT:
                await self._handle_llm_result(event)
            elif event.type == LLM_CALL_COMPLETED:
                await self._handle_llm_completed(event)
            elif event.type == TOOL_CALL_RESULT:
                await self._handle_tool_result(event)
            self._consecutive_errors = 0
        except Exception as exc:
            self._consecutive_errors += 1
            logger.exception("Worker error in session %s", self.session_id)
            if self._consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS:
                await self.bus.publish(EventEnvelope(
                    type=ERROR_RAISED,
                    session_id=self.session_id,
                    source="agent",
                    payload={
                        "error_type": "WorkerCrash",
                        "error_message": (
                            f"Worker crashed after {self.MAX_CONSECUTIVE_ERRORS} "
                            f"consecutive errors: {exc}"
                        ),
                    },
                ))

    async def _handle_turn_cancel_requested(self, event: EventEnvelope) -> None:
        """取消当前活跃轮次，后续同 turn 事件将被忽略。"""
        latest_turn = self.rt.state_store.latest_turn(self.session_id)
        turn_id = event.turn_id or (latest_turn.turn_id if latest_turn else None)
        if not turn_id:
            logger.info("收到取消请求但当前无活跃 turn session=%s", self.session_id)
            return
        if self.rt.state_store.is_turn_cancelled(self.session_id, turn_id):
            return

        reason = str(event.payload.get("reason", "user_cancel"))
        self.rt.state_store.mark_turn_cancelled(self.session_id, turn_id)
        await self.rt.repo.update_turn_status(turn_id, status="cancelled", agent_response=reason)
        await self.bus.publish(
            EventEnvelope(
                type=ERROR_RAISED,
                session_id=self.session_id,
                turn_id=turn_id,
                trace_id=event.trace_id,
                source="agent",
                payload={
                    "error_type": "TurnCancelled",
                    "error_message": reason,
                    "context": {"cancelled": True},
                },
            )
        )
        logger.info("已取消 turn session=%s turn=%s reason=%s", self.session_id, turn_id, reason)

    async def _handle_user_input(self, event: EventEnvelope) -> None:
        content = str(event.payload.get("content", ""))
        turn_id = event.turn_id or f"turn_{uuid.uuid4().hex[:12]}"

        await self.rt.repo.create_session(self.session_id, meta={"title": content[:20] or "新会话"})
        await self.rt.repo.update_session_activity(self.session_id)
        await self.rt.repo.create_turn(turn_id=turn_id, session_id=self.session_id, user_input=content)

        # v0.5: 首轮加载 workspace 文件
        context_files = None
        if self.rt.state_store.is_first_turn(self.session_id):
            from agentos.platform.config.workspace import load_workspace_files
            workspace_dir = config.get("system.workspace_dir", "./SenseAssistant/workspace")
            context_files = await load_workspace_files(workspace_dir)
            self.rt.state_store.mark_first_turn_done(self.session_id)

        # 从内存或 SQLite 惰性加载历史消息
        history = await self.rt.state_store.load_session_history(
            self.session_id, self.rt.repo,
        )

        # v0.6: 加载 MEMORY.md 注入 system prompt
        memory_context = None
        if self.rt.memory_manager:
            memory_context = await self.rt.memory_manager.load_memory_md()

        messages = self.rt.context_builder.build_messages(
            content, history,
            memory_context=memory_context,
            context_files=context_files,
            agent_config=self.agent_config,
        )
        state = TurnState(turn_id=turn_id, user_input=content, messages=messages)
        # 记录新消息的起始位置：跳过 system prompt(1条) + 旧历史
        state.history_offset = 1 + len(history)
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
                    "provider": self._get_provider(),
                    "model": self._get_model(),
                    "messages": messages,
                    "tools": self._get_filtered_tools(),
                    "temperature": self._get_temperature(),
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
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        # 透传 Gemini thought signature 相关字段
        for extra_key in ("reasoning_details", "provider_specific_fields"):
            if response.get(extra_key):
                assistant_msg[extra_key] = response[extra_key]
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

        # 只保存本轮新消息到历史（跳过 system prompt + 旧历史）
        new_messages = state.messages[state.history_offset:]
        self.rt.state_store.append_to_history(event.session_id, new_messages)

        # 持久化新消息到 SQLite
        for msg in new_messages:
            role = msg.get("role", "")
            if role == "system":
                continue
            tool_calls_json = None
            if msg.get("tool_calls"):
                tool_calls_json = json.dumps(msg["tool_calls"], ensure_ascii=False)
            await self.rt.repo.save_message(
                session_id=event.session_id,
                turn_id=event.turn_id,
                role=role,
                content=msg.get("content"),
                tool_calls=tool_calls_json,
                tool_call_id=msg.get("tool_call_id"),
                tool_name=msg.get("name"),
            )

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
                    "provider": self._get_provider(),
                    "model": self._get_model(),
                    "messages": state.messages,
                    "tools": self._get_filtered_tools(),
                    "temperature": self._get_temperature(),
                },
            )
        )

    async def _handle_agent_message_completed(self, event: EventEnvelope) -> None:
        """将异步子 Agent 结果转成新一轮 USER_INPUT。"""
        agent_id = str(event.payload.get("agent_id", "unknown-agent"))
        result = str(event.payload.get("result", ""))
        record_id = str(event.payload.get("record_id", ""))
        attempt_count = int(event.payload.get("attempt_count", 1) or 1)
        max_attempts = int(event.payload.get("max_attempts", 1) or 1)
        trace_text = f"记录ID: {record_id}\n" if record_id else ""
        follow_up = (
            f"来自 {agent_id} 的异步结果如下：\n{trace_text}"
            f"尝试次数: {attempt_count}/{max_attempts}\n\n{result}\n\n"
            "请基于这个结果继续处理当前任务。"
        )
        await self._handle_user_input(
            EventEnvelope(
                type=USER_INPUT,
                session_id=event.session_id,
                source="agent_message",
                payload={"content": follow_up},
            )
        )

    async def _handle_agent_message_failed(self, event: EventEnvelope) -> None:
        """将异步失败结果转成新一轮 USER_INPUT。"""
        agent_id = str(event.payload.get("agent_id", "unknown-agent"))
        error = str(event.payload.get("error", "未知错误"))
        record_id = str(event.payload.get("record_id", ""))
        attempt_count = int(event.payload.get("attempt_count", 1) or 1)
        max_attempts = int(event.payload.get("max_attempts", 1) or 1)
        trace_text = f"记录ID: {record_id}\n" if record_id else ""
        follow_up = (
            f"来自 {agent_id} 的异步任务失败：\n{trace_text}"
            f"尝试次数: {attempt_count}/{max_attempts}\n\n{error}\n\n"
            "请根据失败原因决定是否重试、改道或直接回复用户。"
        )
        await self._handle_user_input(
            EventEnvelope(
                type=USER_INPUT,
                session_id=event.session_id,
                source="agent_message",
                payload={"content": follow_up},
            )
        )
