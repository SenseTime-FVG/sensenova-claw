from __future__ import annotations

import json
from typing import Any, AsyncIterator

from anthropic import AsyncAnthropic

from sensenova_claw.platform.config.config import config
from sensenova_claw.adapters.llm.base import LLMProvider


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

        response = await self.client.messages.create(**req, extra_body=extra_body)

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

    async def stream_call(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
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

        tool_calls_acc: dict[int, dict[str, Any]] = {}
        tool_idx = 0
        usage: dict[str, int] = {}

        async with self.client.messages.stream(**req, extra_body=extra_body) as stream:
            async for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        tool_calls_acc[tool_idx] = {
                            "id": block.id,
                            "name": block.name,
                            "arguments": "",
                        }
                elif event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        yield {"type": "delta", "content": delta.text}
                    elif delta.type == "thinking_delta":
                        yield {"type": "delta", "reasoning_content": getattr(delta, "thinking", "")}
                    elif delta.type == "input_json_delta":
                        if tool_idx in tool_calls_acc:
                            tool_calls_acc[tool_idx]["arguments"] += delta.partial_json
                elif event.type == "content_block_stop":
                    if tool_idx in tool_calls_acc:
                        tool_idx += 1
                elif event.type == "message_delta":
                    pass
                elif event.type == "message_start":
                    msg_usage = getattr(event.message, "usage", None)
                    if msg_usage:
                        usage["prompt_tokens"] = getattr(msg_usage, "input_tokens", 0)

        final_msg = await stream.get_final_message()
        out_tokens = final_msg.usage.output_tokens if final_msg.usage else 0
        usage["completion_tokens"] = out_tokens
        usage["total_tokens"] = usage.get("prompt_tokens", 0) + out_tokens

        assembled: list[dict[str, Any]] = []
        for idx in sorted(tool_calls_acc.keys()):
            tc = tool_calls_acc[idx]
            args_str = tc["arguments"]
            try:
                parsed = json.loads(args_str) if args_str else {}
            except (json.JSONDecodeError, TypeError):
                parsed = args_str
            assembled.append({"id": tc["id"], "name": tc["name"], "arguments": parsed})

        finish_reason = "tool_calls" if assembled else (final_msg.stop_reason or "stop")
        yield {"type": "finish", "finish_reason": finish_reason, "usage": usage, "tool_calls": assembled}

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
