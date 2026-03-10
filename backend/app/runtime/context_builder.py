from __future__ import annotations

import json
import platform
import sys
from datetime import datetime
from typing import Any, TYPE_CHECKING

from app.core.config import config
from app.runtime.prompt_builder import (
    ContextFile,
    RuntimeInfo,
    SystemPromptParams,
    build_system_prompt,
)

if TYPE_CHECKING:
    from app.skills.registry import SkillRegistry
    from app.tools.registry import ToolRegistry


class ContextBuilder:
    def __init__(
        self,
        skill_registry: SkillRegistry | None = None,
        tool_registry: ToolRegistry | None = None,
    ):
        self.skill_registry = skill_registry
        self.tool_registry = tool_registry

    def build_messages(
        self,
        user_input: str,
        history: list[dict[str, Any]] | None = None,
        memory_context: str | None = None,
        context_files: list[ContextFile] | None = None,
    ) -> list[dict[str, Any]]:
        """构建 LLM 调用的完整消息列表"""
        # 收集工具信息
        tool_names: list[str] = []
        tool_summaries: dict[str, str] = {}
        if self.tool_registry:
            for t in self.tool_registry.as_llm_tools():
                tool_names.append(t["name"])
                tool_summaries[t["name"]] = t.get("description", "")

        params = SystemPromptParams(
            base_prompt=config.get("agent.system_prompt", ""),
            tool_names=tool_names,
            tool_summaries=tool_summaries,
            skills_prompt=self._build_skills_section(),
            memory_context=memory_context,
            context_files=context_files or [],
            extra_system_prompt=config.get("agent.extra_system_prompt"),
            runtime_info=self._collect_runtime_info(),
        )
        system_prompt = build_system_prompt(params)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]
        if history:
            messages.extend(history)

        # 在用户消息前添加当前时间
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_message = f"[{current_time}] {user_input}"
        messages.append({"role": "user", "content": user_message})
        return messages

    def append_tool_result(
        self,
        messages: list[dict[str, Any]],
        tool_name: str,
        result: Any,
        tool_call_id: str | None = None,
    ) -> list[dict[str, Any]]:
        next_messages = list(messages)
        content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
        tool_message: dict[str, Any] = {
            "role": "tool",
            "name": tool_name,
            "content": content,
        }
        if tool_call_id:
            tool_message["tool_call_id"] = tool_call_id
        next_messages.append(tool_message)
        return next_messages

    def _build_skills_section(self) -> str | None:
        """格式化 skills 列表为 prompt 文本"""
        if not self.skill_registry:
            return None
        skills = self.skill_registry.get_all()
        if not skills:
            return None
        lines = ["<available_skills>"]
        for skill in skills:
            lines.append(f"- {skill.name}: {skill.description}")
        lines.append("</available_skills>")
        return "\n".join(lines)

    def _collect_runtime_info(self) -> RuntimeInfo:
        """收集运行时信息"""
        return RuntimeInfo(
            os=f"{platform.system()} ({platform.machine()})",
            python=platform.python_version(),
            model=config.get("agent.default_model"),
            channel=None,  # 由调用方根据场景填充
        )
