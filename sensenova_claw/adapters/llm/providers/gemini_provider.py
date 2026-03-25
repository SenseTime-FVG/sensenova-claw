from __future__ import annotations

import json
import logging
from copy import deepcopy
from typing import Any

from openai import AsyncOpenAI

from sensenova_claw.platform.config.config import config
from sensenova_claw.adapters.llm.base import LLMProvider

logger = logging.getLogger(__name__)


def _extract_reasoning_details(message: dict[str, Any]) -> list[dict[str, Any]]:
    """从 assistant 消息中提取 reasoning_details（兼容两种格式）"""
    # 格式1: 直接在顶层（Cloudsway 实际返回）
    rd = message.get("reasoning_details")
    if isinstance(rd, list) and rd:
        return rd
    # 格式2: 嵌套在 provider_specific_fields 下（文档描述）
    psf = message.get("provider_specific_fields") or {}
    rd = psf.get("reasoning_details") or []
    return rd if isinstance(rd, list) else []


def has_thought_signature(message: dict[str, Any]) -> bool:
    """检测 assistant 消息是否包含 Gemini thought signature"""
    return any(
        isinstance(item, dict)
        and item.get("type") == "tool"
        and bool(item.get("signature"))
        for item in _extract_reasoning_details(message)
    )


class GeminiProvider(LLMProvider):
    """Gemini via Cloudsway（OpenAI 兼容网关），支持 thought signature 透传"""

    def __init__(self, provider_id: str = "gemini", source_type: str | None = None):
        provider_cfg = config.get(f"llm.providers.{provider_id}", {})
        self.provider_id = provider_id
        self.source_type = source_type or str(provider_cfg.get("source_type", "gemini") or "gemini")
        self.client = AsyncOpenAI(
            api_key=provider_cfg.get("api_key"),
            base_url=provider_cfg.get("base_url") or None,
            timeout=provider_cfg.get("timeout", 120),
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
        normalized_messages = self._clean_messages(messages)

        req: dict[str, Any] = {
            "model": model,
            "messages": normalized_messages,
            "temperature": temperature,
        }
        if tools:
            req["tools"] = [{"type": "function", "function": t} for t in tools]
        if max_tokens:
            req["max_tokens"] = max_tokens
        if extra_body:
            req["extra_body"] = extra_body

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

        # 提取 reasoning_details（含 thought signature）
        # Cloudsway 直接将其放在 message 顶层的 model_extra 中
        extra = getattr(message, "model_extra", None) or {}
        reasoning_details = extra.get("reasoning_details")

        # 兼容 provider_specific_fields 包装格式
        if not reasoning_details:
            psf = extra.get("provider_specific_fields") or {}
            reasoning_details = psf.get("reasoning_details")

        if reasoning_details:
            result["reasoning_details"] = reasoning_details
            logger.debug("Gemini thought signature detected: %s", reasoning_details)

        return result

    # ── 消息清洗：处理 thought signature 拼接 ──

    def _clean_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        根据 thought signature 规则清洗消息列表：
        - 带 signature 的 assistant 消息需保留 provider_specific_fields
        - 紧随其后的 tool 消息需改写为 role=user
        """
        cleaned: list[dict[str, Any]] = []
        pending_google_tool_reply = False

        for msg in messages:
            if pending_google_tool_reply and msg.get("role") == "tool":
                cleaned.append(self._normalize_tool_message_for_google(msg))
                continue

            if msg.get("role") == "assistant" and has_thought_signature(msg):
                cleaned.append(self._rebuild_assistant_message(msg))
            elif msg.get("role") == "assistant":
                cleaned.append(self._normalize_assistant_message(msg))
            elif msg.get("role") == "tool":
                cleaned.append(self._normalize_tool_message(msg))
            else:
                cleaned.append(dict(msg))

            pending_google_tool_reply = has_thought_signature(msg)

        return cleaned

    def _rebuild_assistant_message(self, message: dict[str, Any]) -> dict[str, Any]:
        """保留 reasoning_details 的 assistant 消息重建"""
        payload: dict[str, Any] = {
            k: deepcopy(v)
            for k, v in message.items()
            if k in {"role", "content", "name"}
        }
        tool_calls = message.get("tool_calls")
        if tool_calls:
            payload["tool_calls"] = [self._normalize_tool_call(tc) for tc in tool_calls]
        # 保留 reasoning_details（直接顶层或 provider_specific_fields 包装）
        rd = message.get("reasoning_details")
        if rd:
            payload["reasoning_details"] = deepcopy(rd)
        psf = message.get("provider_specific_fields")
        if psf:
            payload["provider_specific_fields"] = deepcopy(psf)
        return payload

    def _normalize_tool_message_for_google(self, message: dict[str, Any]) -> dict[str, Any]:
        """thought signature 之后的 tool 消息需改写为 role=user"""
        return {
            "role": "user",
            "tool_call_id": message.get("tool_call_id"),
            "content": message.get("content", ""),
        }

    def _normalize_assistant_message(self, message: dict[str, Any]) -> dict[str, Any]:
        result = dict(message)
        tool_calls = result.get("tool_calls") or []
        if tool_calls:
            result["tool_calls"] = [self._normalize_tool_call(tc) for tc in tool_calls]
        result.pop("provider_specific_fields", None)
        return result

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
            normalized["tool_call_id"] = str(normalized["name"])
        normalized.pop("provider_specific_fields", None)
        return normalized
