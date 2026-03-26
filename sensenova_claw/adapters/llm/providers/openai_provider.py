from __future__ import annotations

import json
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from sensenova_claw.platform.config.config import config
from sensenova_claw.adapters.llm.base import (
    DEFAULT_LLM_TEMPERATURE,
    LLMProvider,
    merge_sampling_extra_body,
)


class OpenAIProvider(LLMProvider):
    def __init__(self, provider_id: str = "openai", source_type: str | None = None):
        provider_cfg = config.get(f"llm.providers.{provider_id}", {})
        self.provider_id = provider_id
        self.source_type = source_type or str(provider_cfg.get("source_type", "openai") or "openai")
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
        temperature: float = DEFAULT_LLM_TEMPERATURE,
        max_tokens: int | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_messages = self._normalize_messages(messages)
        merged_extra_body = merge_sampling_extra_body(extra_body)
        req: dict[str, Any] = {
            "model": model,
            "messages": normalized_messages,
            "temperature": temperature,
        }
        if tools:
            req["tools"] = [{"type": "function", "function": t} for t in tools]
        if max_tokens:
            req["max_tokens"] = max_tokens
        if merged_extra_body:
            req["extra_body"] = merged_extra_body

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

        # 提取 reasoning_content（DeepSeek、MiniMax 等 OpenAI 兼容模型的思考过程）
        reasoning_content = getattr(message, "reasoning_content", None) or ""
        result: dict[str, Any] = {
            "content": message.content or "",
            "tool_calls": tool_calls,
            "finish_reason": "tool_calls" if tool_calls else (choice.finish_reason or "stop"),
            "usage": {
                "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
                "completion_tokens": getattr(response.usage, "completion_tokens", 0),
                "total_tokens": getattr(response.usage, "total_tokens", 0),
            },
        }
        if reasoning_content:
            result["reasoning_details"] = [{"type": "thinking", "thinking": reasoning_content}]
        return result

    async def stream_call(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = DEFAULT_LLM_TEMPERATURE,
        max_tokens: int | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        normalized_messages = self._normalize_messages(messages)
        merged_extra_body = merge_sampling_extra_body(extra_body)
        req: dict[str, Any] = {
            "model": model,
            "messages": normalized_messages,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            req["tools"] = [{"type": "function", "function": t} for t in tools]
        if max_tokens:
            req["max_tokens"] = max_tokens
        if merged_extra_body:
            req["extra_body"] = merged_extra_body

        stream = await self.client.chat.completions.create(**req)
        tool_calls_acc: dict[int, dict[str, Any]] = {}
        finish_reason = "stop"
        usage = {}

        async for chunk in stream:
            if chunk.usage:
                usage = {
                    "prompt_tokens": chunk.usage.prompt_tokens or 0,
                    "completion_tokens": chunk.usage.completion_tokens or 0,
                    "total_tokens": chunk.usage.total_tokens or 0,
                }

            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            if choice.finish_reason:
                finish_reason = choice.finish_reason

            content_delta = getattr(delta, "content", None) or ""
            reasoning_delta = getattr(delta, "reasoning_content", None) or ""

            if content_delta or reasoning_delta:
                chunk_data: dict[str, Any] = {"type": "delta"}
                if content_delta:
                    chunk_data["content"] = content_delta
                if reasoning_delta:
                    chunk_data["reasoning_content"] = reasoning_delta
                yield chunk_data

            if delta and delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {
                            "id": tc_delta.id or "",
                            "name": (tc_delta.function.name if tc_delta.function else "") or "",
                            "arguments": "",
                        }
                    if tc_delta.id:
                        tool_calls_acc[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_calls_acc[idx]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            tool_calls_acc[idx]["arguments"] += tc_delta.function.arguments

        assembled_tool_calls: list[dict[str, Any]] = []
        for idx in sorted(tool_calls_acc.keys()):
            tc = tool_calls_acc[idx]
            args_str = tc["arguments"]
            try:
                parsed = json.loads(args_str) if args_str else {}
            except (json.JSONDecodeError, TypeError):
                parsed = args_str
            assembled_tool_calls.append({
                "id": tc["id"],
                "name": tc["name"],
                "arguments": parsed,
            })

        if assembled_tool_calls:
            finish_reason = "tool_calls"

        yield {
            "type": "finish",
            "finish_reason": finish_reason,
            "usage": usage,
            "tool_calls": assembled_tool_calls,
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
