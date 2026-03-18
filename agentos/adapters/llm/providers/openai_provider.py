from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from agentos.platform.config.config import config
from agentos.adapters.llm.base import LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(self):
        provider_cfg = config.get("llm.providers.openai", {})
        self.client = AsyncOpenAI(
            api_key=provider_cfg.get("api_key"),
            base_url=provider_cfg.get("base_url") or None,
            timeout=provider_cfg.get("timeout", 60),
        )

    async def call(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        normalized_messages = self._normalize_messages(messages)
        req: dict[str, Any] = {
            "model": model,
            "messages": normalized_messages,
            "temperature": temperature,
        }
        if tools:
            req["tools"] = [{"type": "function", "function": t} for t in tools]
        if max_tokens:
            req["max_tokens"] = max_tokens

        response = await self.client.chat.completions.create(**req)
        choice = response.choices[0]
        message = choice.message

        tool_calls: list[dict[str, Any]] = []
        if message.tool_calls:
            for tool_call in message.tool_calls:
                arguments = tool_call.function.arguments
                parsed = json.loads(arguments) if isinstance(arguments, str) else arguments
                tool_calls.append({
                    "id": tool_call.id,
                    "name": tool_call.function.name,
                    "arguments": parsed,
                })

        return {
            "content": message.content or "",
            "tool_calls": tool_calls,
            "finish_reason": "tool_calls" if tool_calls else (choice.finish_reason or "stop"),
            "usage": {
                "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
                "completion_tokens": getattr(response.usage, "completion_tokens", 0),
                "total_tokens": getattr(response.usage, "total_tokens", 0),
            },
        }

    def _normalize_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            if role == "assistant" and isinstance(message.get("tool_calls"), list):
                normalized.append(self._normalize_assistant_message(message))
                continue
            if role == "tool":
                normalized.append(self._normalize_tool_message(message))
                continue
            normalized.append(dict(message))
        return normalized

    def _normalize_assistant_message(self, message: dict[str, Any]) -> dict[str, Any]:
        next_message = dict(message)
        tool_calls = next_message.get("tool_calls") or []
        next_message["tool_calls"] = [self._normalize_tool_call(tc) for tc in tool_calls]
        return next_message

    def _normalize_tool_call(self, tool_call: dict[str, Any]) -> dict[str, Any]:
        if "function" in tool_call:
            normalized = dict(tool_call)
            normalized["type"] = normalized.get("type") or "function"
            function_payload = dict(normalized.get("function") or {})
            arguments = function_payload.get("arguments", "{}")
            function_payload["arguments"] = arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False)
            normalized["function"] = function_payload
            return normalized

        arguments = tool_call.get("arguments", {})
        return {
            "id": tool_call.get("id"),
            "type": "function",
            "function": {
                "name": tool_call.get("name"),
                "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False),
            },
        }

    def _normalize_tool_message(self, message: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(message)
        if "tool_call_id" not in normalized and normalized.get("name"):
            # 兼容老格式：缺失 tool_call_id 时退化为 name，避免请求直接被网关拒绝。
            normalized["tool_call_id"] = str(normalized["name"])
        return normalized
