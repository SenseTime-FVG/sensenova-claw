"""SendMessageTool — Agent 间统一消息发送工具。"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, TYPE_CHECKING

from sensenova_claw.capabilities.tools.base import Tool, ToolRiskLevel
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import AGENT_MESSAGE_REQUESTED

if TYPE_CHECKING:
    from sensenova_claw.capabilities.agents.registry import AgentRegistry
    from sensenova_claw.adapters.storage.repository import Repository
    from sensenova_claw.kernel.events.bus import PublicEventBus
    from sensenova_claw.kernel.runtime.agent_message_coordinator import AgentMessageCoordinator

logger = logging.getLogger(__name__)


class SendMessageTool(Tool):
    name = "send_message"
    description = (
        "向指定 Agent 发送消息。"
        "可新建子会话发起任务，也可复用已有子会话继续对话。"
        "支持 targets 参数同时向多个 Agent 并行发送消息。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "target_agent": {
                "type": "string",
                "description": "目标 Agent 的 ID（单目标模式）",
            },
            "message": {
                "type": "string",
                "description": "要发送的消息内容（单目标模式）",
            },
            "targets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "target_agent": {"type": "string", "description": "目标 Agent ID"},
                        "message": {"type": "string", "description": "消息内容"},
                    },
                    "required": ["target_agent", "message"],
                },
                "description": "多目标并行模式：同时向多个 Agent 发送消息，全部完成后返回结果集。与 target_agent+message 互斥。",
            },
            "session_id": {
                "type": "string",
                "description": "可选。已有子会话 ID，用于继续 ping-pong 对话。",
            },
            "mode": {
                "type": "string",
                "enum": ["sync", "async"],
                "default": "sync",
                "description": "sync 表示等待结果，async 表示异步回传结果。",
            },
            "timeout_seconds": {
                "type": "number",
                "description": "可选。无活动超时秒数（子 Agent 有活动时自动续期），默认使用系统配置。",
            },
            "max_retries": {
                "type": "integer",
                "description": "可选。失败后的自动重试次数，默认使用系统配置。",
            },
        },
        "required": [],
    }
    risk_level = ToolRiskLevel.MEDIUM

    def __init__(
        self,
        agent_registry: AgentRegistry,
        bus: PublicEventBus,
        repo: Repository,
        coordinator: AgentMessageCoordinator,
        timeout: float = 300,
        default_max_retries: int = 0,
        max_tool_calls: int = 30,
        max_llm_calls: int = 15,
    ):
        self._registry = agent_registry
        self._bus = bus
        self._repo = repo
        self._coordinator = coordinator
        self._timeout = timeout
        self._default_max_retries = default_max_retries
        self._max_tool_calls = max_tool_calls
        self._max_llm_calls = max_llm_calls

    async def execute(self, **kwargs: Any) -> Any:
        # 多目标并行模式
        targets = kwargs.get("targets")
        if targets and isinstance(targets, list) and len(targets) > 0:
            return await self._execute_parallel(targets, kwargs)

        # 单目标模式（原有逻辑）
        return await self._execute_single(kwargs)

    async def _execute_parallel(self, targets: list[dict], kwargs: dict[str, Any]) -> Any:
        """多目标并行执行：同时向多个 Agent 发送消息，全部完成后返回结果集。"""
        if len(targets) < 2:
            # 只有一个目标时退化为单目标模式
            single = dict(kwargs)
            single["target_agent"] = targets[0].get("target_agent", "")
            single["message"] = targets[0].get("message", "")
            single.pop("targets", None)
            return await self._execute_single(single)

        timeout_seconds = kwargs.get("timeout_seconds") or self._timeout

        async def _send_one(target: dict) -> dict[str, Any]:
            single_kwargs = dict(kwargs)
            single_kwargs["target_agent"] = target.get("target_agent", "")
            single_kwargs["message"] = target.get("message", "")
            single_kwargs["mode"] = "sync"
            single_kwargs["timeout_seconds"] = timeout_seconds
            single_kwargs.pop("targets", None)
            single_kwargs.pop("session_id", None)  # 并行模式不支持复用会话
            try:
                result = await self._execute_single(single_kwargs)
                return {
                    "target_agent": target.get("target_agent", ""),
                    "status": "completed",
                    "result": result,
                }
            except Exception as exc:
                return {
                    "target_agent": target.get("target_agent", ""),
                    "status": "failed",
                    "error": str(exc),
                }

        logger.info(
            "send_message parallel: %d targets [%s]",
            len(targets),
            ", ".join(t.get("target_agent", "?") for t in targets),
        )

        results = await asyncio.gather(*[_send_one(t) for t in targets])
        return list(results)

    async def _execute_single(self, kwargs: dict[str, Any]) -> Any:
        """单目标执行（原有逻辑）。"""
        target_id = str(kwargs.get("target_agent", "")).strip()
        message = str(kwargs.get("message", "")).strip()
        child_session_id = kwargs.get("session_id")
        mode = str(kwargs.get("mode", "sync")).strip() or "sync"
        timeout_seconds = kwargs.get("timeout_seconds")
        max_retries = kwargs.get("max_retries")
        current_session_id = str(kwargs.get("_session_id", "")).strip()
        current_turn_id = kwargs.get("_turn_id")
        current_tool_call_id = kwargs.get("_tool_call_id")

        if not target_id or not message:
            return "send_message 执行失败：target_agent 和 message 为必填项。"
        if mode not in {"sync", "async"}:
            return "send_message 执行失败：mode 仅支持 sync 或 async。"
        if timeout_seconds is None:
            timeout_seconds = self._timeout
        try:
            timeout_seconds = float(timeout_seconds)
        except (TypeError, ValueError):
            return "send_message 执行失败：timeout_seconds 必须是数字。"
        if timeout_seconds <= 0:
            return "send_message 执行失败：timeout_seconds 必须大于 0。"
        if max_retries is None:
            max_retries = self._default_max_retries
        try:
            max_retries = int(max_retries)
        except (TypeError, ValueError):
            return "send_message 执行失败：max_retries 必须是整数。"
        if max_retries < 0:
            return "send_message 执行失败：max_retries 不能为负数。"

        target_config = self._registry.get(target_id)
        if not target_config:
            return f"发送失败：未找到名为 {target_id} 的 Agent。"

        current_meta = None
        if current_session_id:
            current_meta = await self._repo.get_session_meta(current_session_id)
        current_meta = current_meta or {}
        current_agent_id = str(current_meta.get("agent_id", "default"))
        current_agent = self._registry.get(current_agent_id) or self._registry.get("default")

        if current_agent:
            sendable = self._registry.get_sendable(current_agent_id)
            if sendable and target_id not in {agent.id for agent in sendable}:
                return f"发送失败：当前 Agent 未被授权向 {target_id} 发送消息。"

        current_depth = int(current_meta.get("send_depth", 0) or 0)
        current_send_chain = list(current_meta.get("send_chain", []) or [])
        payload_send_chain = current_send_chain or [current_agent_id]
        max_send_depth = (
            current_agent.max_send_depth
            if current_agent is not None
            else target_config.max_send_depth
        )

        if child_session_id:
            child_session_id = str(child_session_id)
            existing_record = await self._coordinator.get_record_by_session(child_session_id)
            if existing_record and existing_record.target_id != target_id:
                return (
                    f"发送失败：session {child_session_id} 属于 {existing_record.target_id}，"
                    f"与目标 {target_id} 不匹配。"
                )
            existing_meta = await self._repo.get_session_meta(child_session_id)
            if existing_meta:
                existing_target = str(existing_meta.get("agent_id", target_id))
                if existing_target != target_id:
                    return (
                        f"发送失败：session {child_session_id} 绑定的是 {existing_target}，"
                        f"与目标 {target_id} 不匹配。"
                    )
            pingpong_count = await self._coordinator.get_pingpong_count(child_session_id)
            if pingpong_count >= target_config.max_pingpong_turns:
                return (
                    f"发送失败：与 {target_id} 的会话（{child_session_id}）"
                    f"已达到最大往返轮数 {target_config.max_pingpong_turns}。"
                )
        else:
            if current_depth >= max_send_depth:
                return (
                    f"发送失败：当前已达到最大消息传递深度 {max_send_depth}，"
                    "无法继续创建新的子会话。"
                )
            # 允许自我委派（同一 agent 的新 session），拦截真正的循环（A→B→A）
            if target_id in current_send_chain and target_id != current_agent_id:
                chain_str = " -> ".join(current_send_chain + [target_id])
                return f"发送失败：检测到循环链路 {chain_str}。"

        record_id = str(uuid.uuid4())
        waiter = None
        if mode == "sync":
            waiter = self._coordinator.register_sync_waiter(record_id)

        logger.info(
            "send_message request record=%s parent_session=%s target=%s mode=%s timeout=%ss retries=%s reuse_session=%s",
            record_id,
            current_session_id,
            target_id,
            mode,
            timeout_seconds,
            max_retries,
            child_session_id,
        )

        await self._bus.publish(
            EventEnvelope(
                type=AGENT_MESSAGE_REQUESTED,
                session_id=current_session_id or "default",
                turn_id=str(current_turn_id) if current_turn_id else None,
                trace_id=record_id,
                source="send_message_tool",
                payload={
                    "record_id": record_id,
                    "target_id": target_id,
                    "message": message,
                    "mode": mode,
                    "session_id": child_session_id,
                    "depth": current_depth if child_session_id else current_depth + 1,
                    "send_chain": payload_send_chain,
                    "parent_session_id": current_session_id,
                    "parent_turn_id": current_turn_id,
                    "parent_tool_call_id": current_tool_call_id,
                    "timeout_seconds": timeout_seconds,
                    "max_retries": max_retries,
                    "max_tool_calls": self._max_tool_calls,
                    "max_llm_calls": self._max_llm_calls,
                },
            )
        )

        if mode == "async":
            if child_session_id:
                return (
                    f"后续消息已发送给 {target_id}（会话: {child_session_id}）。"
                    "对方完成后结果会自动回传。"
                )
            return (
                f"消息已发送给 {target_id}（任务 ID: {record_id}）。"
                "对方完成后结果会自动回传。"
            )

        assert waiter is not None
        # 超时完全由 coordinator 心跳续期机制控制，
        # cancel_message → _resolve_waiter_or_publish 会 set_result(payload)，
        # 所以 await waiter 在超时时返回 {"status": "timed_out", ...}，
        # 后续第 313 行已有处理。
        try:
            result_payload = await waiter
        except asyncio.CancelledError:
            return f"发送失败：{target_id} 的委托会话被清理。"

        if result_payload.get("status") == "completed":
            next_session_id = str(result_payload.get("child_session_id", ""))
            result = str(result_payload.get("result", ""))
            return (
                f"{target_id} 回复如下：\n\n{result}\n\n"
                f"如需继续对话，请使用 session_id=\"{next_session_id}\"。"
            )

        error = str(result_payload.get("error", "未知错误"))
        if result_payload.get("status") == "timed_out":
            return f"{target_id} 处理超时：{error}"
        if result_payload.get("status") == "cancelled":
            return f"{target_id} 已取消：{error}"
        return f"{target_id} 处理失败：{error}"
