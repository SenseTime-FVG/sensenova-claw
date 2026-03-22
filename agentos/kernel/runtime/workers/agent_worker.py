from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
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
        """解析 provider 名称：从 agent_config.model → llm.models → provider"""
        model_key = self._get_model_key()
        provider, _ = config.resolve_model(model_key)
        # 向后兼容：部分 Agent 仍直接填写 model_id，此时保留显式 provider。
        if provider == "mock" and self.agent_config and self.agent_config.provider:
            return self.agent_config.provider
        return provider

    def _get_model(self) -> str:
        """解析实际 model_id（传给 LLM API 的模型名）"""
        model_key = self._get_model_key()
        provider, model_id = config.resolve_model(model_key)
        if provider == "mock" and self.agent_config and self.agent_config.model:
            return self.agent_config.model
        return model_id

    def _get_model_key(self) -> str:
        """获取 model key（llm.models 中的 key）"""
        if self.agent_config and self.agent_config.model:
            return self.agent_config.model
        return config.get("llm.default_model", "mock")

    def _get_temperature(self) -> float:
        if self.agent_config:
            return self.agent_config.temperature
        return config.get("agent.temperature", 0.2)

    def _get_extra_body(self) -> dict:
        """获取 extra_body：agent 级别覆盖 model 级别"""
        model_key = self._get_model_key()
        model_extra = config.get_model_extra_body(model_key)
        if self.agent_config and self.agent_config.extra_body:
            model_extra.update(self.agent_config.extra_body)
        return model_extra

    def _get_filtered_tools(self) -> list[dict]:
        """根据 Agent 配置过滤可用工具"""
        all_tools = self.rt.tool_registry.as_llm_tools()
        if not self.agent_config or not self.agent_config.tools:
            return all_tools  # 空列表 = 全部工具
        allowed = set(self.agent_config.tools)
        # 始终保留 send_message 工具
        always_keep = {"send_message"}
        return [t for t in all_tools if t["name"] in allowed or t["name"] in always_keep]

    # ── 持久化辅助 ─────────────────────────────────────

    async def _persist_message(
        self,
        session_id: str,
        turn_id: str,
        msg: dict[str, Any],
    ) -> None:
        """立即将单条消息写入 SQLite + JSONL（增量持久化）。"""
        role = msg.get("role", "")
        if role == "system":
            return
        tool_calls_json = None
        if msg.get("tool_calls"):
            tool_calls_json = json.dumps(msg["tool_calls"], ensure_ascii=False)
        await self.rt.repo.save_message(
            session_id=session_id,
            turn_id=turn_id,
            role=role,
            content=msg.get("content"),
            tool_calls=tool_calls_json,
            tool_call_id=msg.get("tool_call_id"),
            tool_name=msg.get("name"),
        )
        await self.rt.repo.increment_message_count(session_id)

        # 同步写入 JSONL 文件（按 agent 分目录）
        if self.rt.jsonl_writer:
            try:
                agent_id = (self.agent_config.id if self.agent_config else "default")
                self.rt.jsonl_writer.append(agent_id, session_id, turn_id, msg)
            except Exception:
                logger.warning("JSONL write failed session=%s", session_id, exc_info=True)

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

        # v0.5: 首轮加载 per-agent workspace 文件
        context_files = None
        if self.rt.state_store.is_first_turn(self.session_id):
            from agentos.platform.config.workspace import load_workspace_files, resolve_agentos_home
            agentos_home = str(resolve_agentos_home(config))
            agent_id = self.agent_config.id if self.agent_config else "default"
            context_files = await load_workspace_files(agentos_home, agent_id=agent_id)
            self.rt.state_store.mark_first_turn_done(self.session_id)

        # 读取前端拖入的用户文件
        user_file_paths = event.payload.get("context_files", [])
        if user_file_paths and isinstance(user_file_paths, list):
            user_files = self._load_user_context_files(user_file_paths)
            context_files = (context_files or []) + user_files

        # 从内存或 SQLite 惰性加载历史消息（必须在 persist_message 之前，避免重复）
        history = await self.rt.state_store.load_session_history(
            self.session_id, self.rt.repo,
        )

        # 上下文压缩：LLM 调用前兜底
        if self.rt.context_compressor:
            try:
                _agent_id = self.agent_config.id if self.agent_config else "default"
                history = await self.rt.context_compressor.compress_if_needed(
                    self.session_id, history, agent_id=_agent_id,
                )
                self.rt.state_store.replace_history(self.session_id, history)
            except Exception:
                logger.warning("上下文压缩失败，使用原始历史 session=%s", self.session_id, exc_info=True)

        # v0.6: 加载 MEMORY.md 注入 system prompt
        memory_context = None
        if self.rt.memory_manager:
            agent_id = self.agent_config.id if self.agent_config else None
            memory_context = await self.rt.memory_manager.load_memory_md(agent_id=agent_id)

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

        # 增量持久化：在 history 加载后保存 user 消息，避免重复
        await self._persist_message(
            self.session_id, turn_id, {"role": "user", "content": content},
        )

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
                    "extra_body": self._get_extra_body(),
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

        # 增量持久化：立即保存 assistant 消息
        await self._persist_message(event.session_id, event.turn_id, assistant_msg)

    def _load_user_context_files(self, paths: list[str]) -> list:
        """读取前端传来的文件路径，转为 ContextFile 对象"""
        from agentos.kernel.runtime.prompt_builder import ContextFile
        files = []
        for p in paths:
            if not isinstance(p, str) or not p.strip():
                continue
            try:
                real_path = os.path.realpath(p)
                if not os.path.isfile(real_path):
                    continue
                content = Path(real_path).read_text(encoding="utf-8", errors="replace")
                name = os.path.basename(real_path)
                files.append(ContextFile(name=name, content=content))
            except (OSError, PermissionError, UnicodeDecodeError):
                logger.warning("无法读取 context_file: %s", p)
                continue
        return files

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
            # 解析 per-agent workdir 注入工具调用事件
            from agentos.platform.config.workspace import resolve_agent_workdir, resolve_agentos_home
            agentos_home = str(resolve_agentos_home(config))
            agent_workdir = resolve_agent_workdir(agentos_home, self.agent_config)

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
                            "_agent_workdir": agent_workdir,
                            "_source_agent_id": self.agent_config.id if self.agent_config else "default",
                        },
                    )
                )
            return

        # 没有工具调用，结束本轮对话
        state.final_response = content
        await self.rt.repo.complete_turn(event.turn_id, agent_response=content)

        # 追加本轮新消息到内存历史（供后续 turn 上下文使用）
        new_messages = state.messages[state.history_offset:]
        self.rt.state_store.append_to_history(event.session_id, new_messages)

        # 注意：消息已在 _handle_user_input / _handle_llm_result / _handle_tool_result
        # 中增量持久化到 SQLite，此处无需再批量保存

        # 上下文压缩：轮末异步压缩
        if self.rt.context_compressor:
            asyncio.create_task(self._compress_history_safe(event.session_id))

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

        if self.rt.memory_manager and hasattr(self.rt.memory_manager, "summarize_turn"):
            agent_id = self.agent_config.id if self.agent_config else None
            asyncio.create_task(
                self._summarize_turn_safe(state.messages, agent_id=agent_id)
            )

    async def _compress_history_safe(self, session_id: str) -> None:
        """异步执行上下文压缩，不影响主流程。"""
        try:
            history = self.rt.state_store.get_session_history(session_id)
            if not history:
                return
            _agent_id = self.agent_config.id if self.agent_config else "default"
            compressed = await self.rt.context_compressor.compress_async(
                session_id, history, agent_id=_agent_id,
            )
            self.rt.state_store.replace_history(session_id, compressed)
        except Exception:
            logger.warning("轮末上下文压缩失败 session=%s", session_id, exc_info=True)

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

        # 增量持久化：立即保存 tool 结果消息
        tool_msg: dict[str, Any] = {
            "role": "tool",
            "content": result if isinstance(result, str) else json.dumps(result, ensure_ascii=False),
            "name": tool_name,
        }
        if tool_call_id:
            tool_msg["tool_call_id"] = str(tool_call_id)
        await self._persist_message(event.session_id, event.turn_id, tool_msg)

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
                    "extra_body": self._get_extra_body(),
                },
            )
        )

    async def _summarize_turn_safe(
        self,
        messages: list[dict[str, Any]],
        agent_id: str | None = None,
    ) -> None:
        """异步执行对话总结，不影响主流程结果返回。"""
        try:
            await self.rt.memory_manager.summarize_turn(
                messages,
                provider=self._get_provider(),
                model=self._get_model(),
                agent_id=agent_id,
            )
        except Exception:
            logger.warning(
                "对话总结失败 session=%s agent=%s",
                self.session_id,
                agent_id,
                exc_info=True,
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
