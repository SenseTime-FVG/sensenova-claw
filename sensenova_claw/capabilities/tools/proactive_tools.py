"""Proactive 任务管理工具

提供三个工具供 LLM 在对话中创建和管理 ProactiveJob：
- CreateProactiveJobTool: 创建主动任务
- ListProactiveJobsTool: 列出所有主动任务
- ManageProactiveJobTool: 启用/禁用/删除任务
"""

from __future__ import annotations

import uuid
from typing import Any

from sensenova_claw.capabilities.tools.base import Tool, ToolRiskLevel
from sensenova_claw.kernel.proactive.models import (
    DeliveryConfig,
    EventTrigger,
    ProactiveJob,
    ProactiveTask,
    SafetyConfig,
    TimeTrigger,
)


def _parse_trigger(trigger_dict: dict) -> TimeTrigger | EventTrigger:
    """将 dict 解析为对应的 Trigger 对象"""
    kind = trigger_dict.get("kind", "time")
    if kind == "time":
        return TimeTrigger(
            cron=trigger_dict.get("cron"),
            every=trigger_dict.get("every"),
        )
    elif kind == "event":
        return EventTrigger(
            event_type=trigger_dict.get("event_type", ""),
            filter=trigger_dict.get("filter"),
            debounce_ms=trigger_dict.get("debounce_ms", 5000),
            exclude_payload=trigger_dict.get("exclude_payload"),
        )
    raise ValueError(f"未知 trigger kind: {kind!r}")


class CreateProactiveJobTool(Tool):
    """从对话中创建主动任务"""

    name = "create_proactive_job"
    description = "创建一个主动任务（ProactiveJob），支持定时、事件两种触发方式"
    risk_level = ToolRiskLevel.HIGH
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "任务名称"},
            "trigger": {
                "type": "object",
                "description": "触发配置，包含 kind(time/event) 及对应字段",
            },
            "task": {
                "type": "object",
                "description": "任务执行配置，包含 prompt 等字段",
            },
            "delivery": {
                "type": "object",
                "description": "投递配置，包含 channels 列表",
            },
            "agent_id": {"type": "string", "description": "执行任务的 agent id，默认 proactive-agent"},
            "safety": {
                "type": "object",
                "description": "安全限制配置",
                "properties": {
                    "max_llm_calls": {"type": "integer", "description": "最大 LLM 调用次数"},
                    "max_duration_ms": {"type": "integer", "description": "最大执行时长（毫秒）"},
                    "max_tool_calls": {"type": "integer", "description": "最大工具调用次数"},
                    "allowed_tools": {"type": "array", "items": {"type": "string"}, "description": "允许使用的工具白名单"},
                    "blocked_tools": {"type": "array", "items": {"type": "string"}, "description": "禁止使用的工具黑名单"},
                    "auto_disable_after_errors": {"type": "integer", "description": "连续失败多少次后自动禁用"},
                },
            },
        },
        "required": ["name", "trigger", "task"],
    }

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    async def execute(self, **kwargs: Any) -> str:
        name = kwargs.get("name", "")
        trigger_dict = kwargs.get("trigger", {})
        task_dict = kwargs.get("task", {})
        delivery_dict = kwargs.get("delivery", {})
        agent_id = kwargs.get("agent_id", "proactive-agent")
        safety_dict = kwargs.get("safety") or {}

        trigger = _parse_trigger(trigger_dict)
        task = ProactiveTask(
            prompt=task_dict.get("prompt", ""),
            use_memory=task_dict.get("use_memory", False),
            system_prompt_override=task_dict.get("system_prompt_override"),
        )
        delivery = DeliveryConfig(
            channels=delivery_dict.get("channels", []),
            feishu_target=delivery_dict.get("feishu_target"),
            summary_prompt=delivery_dict.get("summary_prompt"),
        )

        # 从 safety 参数构建 SafetyConfig，未指定的字段使用默认值
        safety_kwargs: dict[str, Any] = {}
        for int_key in ("max_llm_calls", "max_duration_ms", "max_tool_calls", "auto_disable_after_errors"):
            if int_key in safety_dict:
                safety_kwargs[int_key] = int(safety_dict[int_key])
        for list_key in ("allowed_tools", "blocked_tools"):
            if list_key in safety_dict:
                safety_kwargs[list_key] = safety_dict[list_key]

        job = ProactiveJob(
            id=f"pj-{uuid.uuid4().hex[:8]}",
            name=name,
            agent_id=agent_id,
            enabled=True,
            trigger=trigger,
            task=task,
            delivery=delivery,
            safety=SafetyConfig(**safety_kwargs),
            source="conversation",
        )

        await self._runtime.add_job(job)
        return f"成功创建主动任务「{name}」（id: {job.id}）"


class ListProactiveJobsTool(Tool):
    """列出所有主动任务"""

    name = "list_proactive_jobs"
    description = "列出当前所有已注册的主动任务及其状态"
    risk_level = ToolRiskLevel.LOW
    parameters = {"type": "object", "properties": {}, "required": []}

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    async def execute(self, **kwargs: Any) -> str:
        jobs: list[ProactiveJob] = await self._runtime.list_jobs()
        if not jobs:
            return "当前没有主动任务"
        lines = []
        for job in jobs:
            status = "启用" if job.enabled else "禁用"
            lines.append(f"- [{status}] {job.name} (id: {job.id}, source: {job.source})")
        return "\n".join(lines)


class ManageProactiveJobTool(Tool):
    """启用、禁用或删除主动任务"""

    name = "manage_proactive_job"
    description = "对指定主动任务执行 enable/disable/delete 操作"
    risk_level = ToolRiskLevel.MEDIUM
    parameters = {
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "任务 id"},
            "action": {
                "type": "string",
                "enum": ["enable", "disable", "delete"],
                "description": "操作类型",
            },
        },
        "required": ["job_id", "action"],
    }

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    async def execute(self, **kwargs: Any) -> str:
        job_id: str = kwargs["job_id"]
        action: str = kwargs["action"]

        if action == "enable":
            await self._runtime.set_job_enabled(job_id, True)
            return f"任务 {job_id} 已启用"
        elif action == "disable":
            await self._runtime.set_job_enabled(job_id, False)
            return f"任务 {job_id} 已禁用"
        elif action == "delete":
            await self._runtime.remove_job(job_id)
            return f"任务 {job_id} 已删除"
        else:
            return f"未知操作: {action!r}，支持 enable/disable/delete"
