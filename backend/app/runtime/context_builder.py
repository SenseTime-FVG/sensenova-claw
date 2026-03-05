from __future__ import annotations

import json
from typing import Any

from app.core.config import config


class ContextBuilder:
    def build_messages(self, user_input: str, history: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": config.get("agent.system_prompt")},
        ]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_input})
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
