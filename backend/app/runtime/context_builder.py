from __future__ import annotations

import json
import platform
from datetime import datetime
from typing import Any, TYPE_CHECKING

from app.core.config import config

if TYPE_CHECKING:
    from app.skills.registry import SkillRegistry


class ContextBuilder:
    def __init__(self, skill_registry: SkillRegistry | None = None):
        self.skill_registry = skill_registry

    def build_messages(self, user_input: str, history: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        # 获取系统信息和当前时间
        system_type = platform.system()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        base_prompt = config.get("agent.system_prompt", "")
        system_prompt = f"{base_prompt}\n\n系统类型: {system_type}\n当前时间: {current_time}"

        # 注入 skills
        if self.skill_registry:
            skills = self.skill_registry.get_all()
            if skills:
                skills_section = "\n\n<available_skills>\n"
                for skill in skills:
                    skills_section += f"- {skill.name}: {skill.description}\n"
                skills_section += "</available_skills>"
                system_prompt += skills_section

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]
        if history:
            messages.extend(history)

        # 在用户消息前添加当前时间
        current_time_for_user = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_message = f"[{current_time_for_user}] {user_input}"
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
