from __future__ import annotations

import json
from typing import Any

from anthropic import AsyncAnthropic

from agentos.platform.config.config import config
from agentos.adapters.llm.base import LLMProvider


class AnthropicProvider(LLMProvider):
    def __init__(self):
        provider_cfg = config.get("llm.providers.anthropic", {})
        self.client = AsyncAnthropic(
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
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        system_messages = [m for m in messages if m.get("role") == "system"]
        non_system_messages = [m for m in messages if m.get("role") != "system"]

        system_prompt = "\n\n".join(m.get("content", "") for m in system_messages) if system_messages else None

        normalized_messages = self._normalize_messages(non_system_messages)

        req: dict[str, Any] = {
            "model": model,
            "messages": normalized_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
        }

        if system_prompt:
            req["system"] = system_prompt

        if tools:
            req["tools"] = [self._convert_tool(t) for t in tools]

        # 合并 extra_body 到请求参数（Anthropic SDK 直接接受关键字参数）
        if extra_body:
            req.update(extra_body)

        response = await self.client.messages.create(**req)

        content_text = ""
        tool_calls: list[dict[str, Any]] = []

        for block in response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input,
                })

        return {
            "content": content_text,
            "tool_calls": tool_calls,
            "finish_reason": "tool_calls" if tool_calls else response.stop_reason,
            "usage": {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            },
        }

    def _convert_tool(self, tool: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": tool.get("name"),
            "description": tool.get("description", ""),
            "input_schema": tool.get("parameters", {}),
        }

    def _normalize_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            if role == "assistant":
                normalized.append(self._normalize_assistant_message(message))
            elif role == "tool":
                normalized.append(self._normalize_tool_message(message))
            else:
                normalized.append({"role": role, "content": message.get("content", "")})
        return normalized

    def _normalize_assistant_message(self, message: dict[str, Any]) -> dict[str, Any]:
        content: list[dict[str, Any]] = []

        if message.get("content"):
            content.append({"type": "text", "text": message["content"]})

        tool_calls = message.get("tool_calls") or []
        for tc in tool_calls:
            content.append({
                "type": "tool_use",
                "id": tc.get("id"),
                "name": tc.get("name"),
                "input": tc.get("arguments", {}),
            })

        return {"role": "assistant", "content": content}

    def _normalize_tool_message(self, message: dict[str, Any]) -> dict[str, Any]:
        tool_call_id = message.get("tool_call_id") or message.get("name", "")
        content_str = message.get("content", "")

        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": content_str,
                }
            ],
        }
