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
        }
        if temperature is not None:
            req["temperature"] = temperature
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
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if temperature is not None:
            req["temperature"] = temperature
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

    # 默认启用 thinking 的 source_type（这些模型的 API 要求 assistant tool_call 消息携带 reasoning_content）
    _THINKING_SOURCE_TYPES = {"kimi"}

    def _normalize_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # 检测对话中是否启用了 thinking：
        # 1. source_type 为已知 thinking 模型
        # 2. 或对话历史中任意 assistant 消息含 reasoning_content/reasoning_details
        has_thinking = self.source_type in self._THINKING_SOURCE_TYPES or any(
            msg.get("role") == "assistant"
            and (msg.get("reasoning_content") or msg.get("reasoning_details"))
            for msg in messages
        )

        normalized: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            if role == "assistant" and isinstance(message.get("tool_calls"), list):
                normalized.append(self._normalize_assistant_message(message, has_thinking))
                continue
            if role == "tool":
                normalized.append(self._normalize_tool_message(message))
                continue
            normalized.append(dict(message))
        return normalized

    def _normalize_assistant_message(
        self, message: dict[str, Any], has_thinking: bool = False,
    ) -> dict[str, Any]:
        next_message = dict(message)
        tool_calls = next_message.get("tool_calls") or []
        next_message["tool_calls"] = [self._normalize_tool_call(tc) for tc in tool_calls]

        # 从 reasoning_details 还原 reasoning_content（Kimi/DeepSeek 等需要）
        reasoning_details = next_message.pop("reasoning_details", None)
        if reasoning_details and "reasoning_content" not in next_message:
            for detail in reasoning_details:
                if isinstance(detail, dict) and detail.get("type") == "thinking":
                    next_message["reasoning_content"] = detail.get("thinking", "")
                    break

        # 当对话启用了 thinking 时，确保所有带 tool_calls 的 assistant 消息都有 reasoning_content
        # （Kimi 等模型要求：thinking is enabled 时 assistant tool call 消息必须携带此字段）
        if has_thinking and "reasoning_content" not in next_message:
            next_message["reasoning_content"] = ""

        # 清理非标准字段，避免被 OpenAI 兼容 API 拒绝
        next_message.pop("provider_specific_fields", None)

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
