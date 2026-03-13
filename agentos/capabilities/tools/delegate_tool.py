"""DelegateTool — Agent 间委托的桥梁工具。

允许一个 Agent 将子任务委托给另一个 Agent。
内部机制：
1. 创建子 session（绑定到目标 Agent 的配置）
2. 向子 session 注入委托任务作为 user.input
3. 等待子 session 的 agent.step_completed 事件
4. 将子 Agent 的最终响应作为工具结果返回

对调用方（LLM）表现为同步调用，内部通过事件系统异步执行。
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from typing import Any, TYPE_CHECKING

from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import (
    AGENT_STEP_COMPLETED,
    ERROR_RAISED,
    USER_INPUT,
)
from agentos.capabilities.tools.base import Tool, ToolRiskLevel

if TYPE_CHECKING:
    from agentos.capabilities.agents.registry import AgentRegistry
    from agentos.adapters.storage.repository import Repository
    from agentos.kernel.events.router import BusRouter

logger = logging.getLogger(__name__)


class DelegateTool(Tool):
    name = "delegate"
    description = (
        "将子任务委托给另一个专门的 Agent 处理。"
        "target_agent: 目标 Agent 的 ID。"
        "task: 要委托的任务描述。"
        "context: 需要传递给目标 Agent 的上下文信息（可选）。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "target_agent": {
                "type": "string",
                "description": "目标 Agent 的 ID",
            },
            "task": {
                "type": "string",
                "description": "要委托的任务描述",
            },
            "context": {
                "type": "string",
                "description": "传递给目标 Agent 的上下文信息",
            },
        },
        "required": ["target_agent", "task"],
    }
    risk_level = ToolRiskLevel.MEDIUM

    def __init__(
        self,
        agent_registry: AgentRegistry,
        bus_router: BusRouter,
        repo: Repository,
        timeout: float = 300,
    ):
        self._registry = agent_registry
        self._bus_router = bus_router
        self._repo = repo
        self._timeout = timeout

    async def execute(self, **kwargs: Any) -> Any:
        target_id = kwargs.get("target_agent", "")
        task = kwargs.get("task", "")
        context = kwargs.get("context", "")
        current_session_id = kwargs.get("_session_id", "")

        # 1. 验证目标 Agent 存在
        target_config = self._registry.get(target_id)
        if not target_config:
            return {"success": False, "error": f"Agent '{target_id}' not found"}

        # 2. 检查委托深度
        current_depth = 0
        if current_session_id:
            meta = await self._repo.get_session_meta(current_session_id)
            if meta:
                current_depth = meta.get("delegation_depth", 0)

        if current_depth >= target_config.max_delegation_depth:
            return {"success": False, "error": "Maximum delegation depth exceeded"}

        # 3. 创建子 session
        sub_session_id = f"delegate_{uuid.uuid4().hex[:12]}"
        await self._repo.create_session(
            session_id=sub_session_id,
            meta={
                "title": f"[delegate] {task[:30]}",
                "agent_id": target_id,
                "parent_session_id": current_session_id,
                "delegation_depth": current_depth + 1,
            },
        )

        # 4. 构造用户输入
        user_input = task
        if context:
            user_input = f"上下文信息：\n{context}\n\n任务：\n{task}"

        # 5. 启动 listener（必须在发布 USER_INPUT 之前订阅，防止竞态）
        result_future: asyncio.Future = asyncio.get_event_loop().create_future()

        async def _listener():
            async for event in self._bus_router.public_bus.subscribe():
                if event.session_id != sub_session_id:
                    continue
                if event.type == AGENT_STEP_COMPLETED:
                    if not result_future.done():
                        result_future.set_result(event.payload)
                    return
                if event.type == ERROR_RAISED:
                    if not result_future.done():
                        result_future.set_result({
                            "success": False,
                            "error": event.payload.get("error_message", "Unknown error"),
                        })
                    return

        listener_task = asyncio.create_task(_listener())
        # 让 listener 有机会注册订阅
        await asyncio.sleep(0)

        # 6. 发布 user.input 到公共总线
        turn_id = f"turn_{uuid.uuid4().hex[:12]}"
        event = EventEnvelope(
            type=USER_INPUT,
            session_id=sub_session_id,
            turn_id=turn_id,
            source="delegate_tool",
            payload={"content": user_input},
        )
        await self._bus_router.public_bus.publish(event)

        # 7. 等待子 session 完成
        try:
            payload = await asyncio.wait_for(result_future, timeout=self._timeout)
            # 检查是否是错误响应（来自 ERROR_RAISED）
            if isinstance(payload, dict) and "error" in payload:
                return payload
            content = payload.get("result", {}).get("content", "")
            return {"success": True, "result": content}
        except asyncio.TimeoutError:
            return {"success": False, "error": f"Delegation timed out after {self._timeout}s"}
        finally:
            listener_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await listener_task
