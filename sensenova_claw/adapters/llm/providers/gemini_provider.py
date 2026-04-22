from __future__ import annotations

import json
import logging
from copy import deepcopy
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from sensenova_claw.platform.config.config import config
from sensenova_claw.adapters.llm.base import (
    DEFAULT_LLM_TEMPERATURE,
    LLMProvider,
    merge_sampling_extra_body,
)

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


def _normalize_reasoning_details(reasoning_details: Any) -> list[dict[str, Any]]:
    """归一化 Gemini reasoning_details，补出前端可展示的 thinking 条目。

    Gemini / 兼容网关在工具调用场景下常返回两类 reasoning 数据：
    1. `type=tool` 的内部签名元数据（用于后续请求续传 thought signature）
    2. 带 `text` / `thinking` / `summary` / `content` 的可读文本

    当前前端只会展示 `type=thinking` 的条目，因此这里在保留原始结构的同时，
    把可读文本补成额外的 `type=thinking` 条目，避免改动事件协议或前端逻辑。
    """
    if not isinstance(reasoning_details, list):
        return []

    normalized: list[dict[str, Any]] = []
    seen_thinking: set[str] = set()
    text_keys = ("thinking", "text", "summary", "content")

    for item in reasoning_details:
        if not isinstance(item, dict):
            continue
        detail = deepcopy(item)
        normalized.append(detail)

        detail_type = str(detail.get("type", "") or "").strip().lower()
        text_value = ""
        for key in text_keys:
            value = detail.get(key)
            if isinstance(value, str) and value.strip():
                text_value = value.strip()
                break

        if not text_value:
            continue

        if detail_type == "thinking":
            seen_thinking.add(text_value)
            continue

        if detail_type == "tool":
            # tool 条目主要是 thought signature 元数据；只有当它真的带了可读文本时，
            # 才额外补一条 thinking 供 UI 展示。
            pass

        if text_value in seen_thinking:
            continue
        seen_thinking.add(text_value)
        normalized.append({"type": "thinking", "thinking": text_value})

    return normalized


def _append_reasoning_content(
    reasoning_details: list[dict[str, Any]],
    reasoning_content: Any,
) -> list[dict[str, Any]]:
    """把 Gemini 返回的 reasoning_content 追加为可展示的 thinking 条目。"""
    if not isinstance(reasoning_content, str) or not reasoning_content.strip():
        return reasoning_details

    text = reasoning_content.strip()
    for item in reasoning_details:
        if (
            isinstance(item, dict)
            and str(item.get("type", "") or "").strip().lower() == "thinking"
            and str(item.get("thinking", "") or "").strip() == text
        ):
            return reasoning_details

    return [*reasoning_details, {"type": "thinking", "thinking": text}]


def _tool_call_has_thought_sig(tc: dict[str, Any]) -> bool:
    """检测单个 tool_call 是否包含 Chat Completions 格式的 thought signature。

    Google Vertex AI Chat Completions 格式:
      tool_call.extra_content.google.thought_signature = "<sig>"
    """
    ec = tc.get("extra_content")
    if isinstance(ec, dict):
        google = ec.get("google")
        if isinstance(google, dict) and google.get("thought_signature"):
            return True
    return False


def has_thought_signature(message: dict[str, Any]) -> bool:
    """检测 assistant 消息是否包含 Gemini thought signature。

    同时兼容两种格式：
    1. Cloudsway: reasoning_details 列表中 type=tool + signature
    2. Google Chat Completions: tool_calls[].extra_content.google.thought_signature
    """
    # 检查 reasoning_details 格式（Cloudsway）
    if any(
        isinstance(item, dict)
        and item.get("type") == "tool"
        and bool(item.get("signature"))
        for item in _extract_reasoning_details(message)
    ):
        return True
    # 检查 tool_calls 上的 extra_content 格式（Google Chat Completions）
    for tc in message.get("tool_calls") or []:
        if isinstance(tc, dict) and _tool_call_has_thought_sig(tc):
            return True
    return False


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

    def _build_extra_body(
        self,
        normalized_messages: list[dict[str, Any]],
        extra_body: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """构造 extra_body，通过 extra_body.messages 覆盖 SDK 序列化。

        OpenAI SDK 序列化 tool_calls 时会剥离非标准字段（如 extra_content），
        导致 Gemini thought signature 丢失。通过 extra_body 传递原始 messages
        可以绕过 SDK 的 TypedDict 序列化，保留所有字段。
        """
        merged = dict(extra_body) if extra_body else {}
        merged = merge_sampling_extra_body(merged)
        merged["messages"] = normalized_messages
        return merged

    async def call(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = DEFAULT_LLM_TEMPERATURE,
        max_tokens: int | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_messages = self._clean_messages(messages)

        # 通过 extra_body 传递 messages，绕过 SDK 对 tool_calls 的序列化限制
        merged_extra = self._build_extra_body(normalized_messages, extra_body)

        req: dict[str, Any] = {
            "model": model,
            "messages": normalized_messages,
            "extra_body": merged_extra,
        }
        if temperature is not None:
            req["temperature"] = temperature
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
                tc_dict: dict[str, Any] = {
                    "id": tool_call.id,
                    "name": tool_call.function.name,
                    "arguments": parsed,
                }
                # 保留 thought signature（Google Chat Completions 格式: extra_content.google.thought_signature）
                tc_extra = getattr(tool_call, "model_extra", None) or {}
                if tc_extra.get("extra_content"):
                    tc_dict["extra_content"] = tc_extra["extra_content"]
                tool_calls.append(tc_dict)

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

        reasoning_content = extra.get("reasoning_content")
        if not reasoning_content:
            psf = extra.get("provider_specific_fields") or {}
            reasoning_content = psf.get("reasoning_content")

        normalized_reasoning_details = _normalize_reasoning_details(reasoning_details)
        normalized_reasoning_details = _append_reasoning_content(
            normalized_reasoning_details,
            reasoning_content,
        )

        if normalized_reasoning_details:
            result["reasoning_details"] = normalized_reasoning_details
            has_tool_sig = any(
                isinstance(item, dict) and item.get("type") == "tool" and item.get("signature")
                for item in normalized_reasoning_details
            )
            logger.debug(
                "Gemini reasoning_details: raw=%d normalized=%d has_tool_signature=%s has_reasoning_content=%s",
                len(reasoning_details) if isinstance(reasoning_details, list) else 0,
                len(normalized_reasoning_details), has_tool_sig,
                bool(isinstance(reasoning_content, str) and reasoning_content.strip()),
            )

        has_ec_sig = any(_tool_call_has_thought_sig(tc) for tc in tool_calls)
        if has_ec_sig:
            logger.debug("Gemini thought signature on tool_calls extra_content detected")

        if tool_calls and not reasoning_details and not has_ec_sig:
            logger.warning(
                "Gemini response has %d tool_calls but NO thought signature "
                "(neither reasoning_details nor extra_content). "
                "model_extra keys: %s",
                len(tool_calls),
                list((getattr(message, "model_extra", None) or {}).keys()),
            )

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
        """Gemini 流式调用回退为非流式 call() + 分块 yield。

        Gemini thinking 模型在流式响应中不会返回结构化 thought signature
        （type=tool, signature=...），导致后续多轮请求缺少必需的 thought_signature。
        通过非流式调用确保完整获取 reasoning_details（含 thought signature），
        再模拟流式 yield 保持事件管道兼容。
        """
        result = await self.call(
            model=model,
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=extra_body,
        )
        if result.get("content"):
            yield {"type": "delta", "content": result["content"]}
        if result.get("reasoning_details"):
            yield {"type": "delta", "reasoning_details": result["reasoning_details"]}
        yield {
            "type": "finish",
            "finish_reason": result.get("finish_reason", "stop"),
            "usage": result.get("usage", {}),
            "tool_calls": result.get("tool_calls", []),
            "reasoning_details": result.get("reasoning_details", []),
        }

    # ── 消息清洗：处理 thought signature 拼接 + function call/response 对齐 ──

    def _clean_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        根据 thought signature 规则清洗消息列表：
        - 带 signature 的 assistant 消息需保留 provider_specific_fields
        - 紧随其后的 tool 消息需改写为 role=user
        最后对齐 function call 和 function response 数量，满足 Gemini 的严格约束。
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
                other = dict(msg)
                other.pop("__compressed__", None)
                other.pop("__phase2_compressed__", None)
                cleaned.append(other)

            pending_google_tool_reply = has_thought_signature(msg)

        return self._align_tool_call_responses(cleaned)

    def _align_tool_call_responses(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """确保每个带 tool_calls 的 assistant 消息后面有数量匹配的 tool 响应。

        Gemini API 要求 function_call parts 数量 == function_response parts 数量，
        否则返回 400。本方法修补以下情况：
        - tool 响应缺失：补一条占位 tool 消息
        - tool 响应多余（孤儿）：移除
        - assistant 的 tool_calls 中某些 call 无对应响应：按 id 补齐
        """
        aligned: list[dict[str, Any]] = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            tool_calls = msg.get("tool_calls") if msg.get("role") == "assistant" else None

            if not tool_calls:
                # 跳过孤儿 tool 消息（前面没有对应的 assistant tool_calls）
                if msg.get("role") == "tool" and aligned and aligned[-1].get("role") != "assistant":
                    has_pending = False
                    for prev in reversed(aligned):
                        if prev.get("role") == "assistant" and prev.get("tool_calls"):
                            has_pending = True
                            break
                        if prev.get("role") in ("user", "system"):
                            break
                    if not has_pending:
                        logger.warning(
                            "Gemini align: 跳过孤儿 tool 消息 tool_call_id=%s",
                            msg.get("tool_call_id"),
                        )
                        i += 1
                        continue
                aligned.append(msg)
                i += 1
                continue

            # 收集 assistant 消息中所有 tool_call id
            expected_ids: list[str] = []
            for tc in tool_calls:
                tc_id = tc.get("id") or tc.get("function", {}).get("name", "")
                expected_ids.append(tc_id)

            aligned.append(msg)
            i += 1

            # 收集后续连续的 tool 消息
            found_ids: set[str] = set()
            tool_msgs: list[dict[str, Any]] = []
            while i < len(messages) and messages[i].get("role") == "tool":
                tool_msg = messages[i]
                tid = tool_msg.get("tool_call_id", "")
                found_ids.add(tid)
                tool_msgs.append(tool_msg)
                i += 1

            if len(tool_msgs) == len(expected_ids):
                aligned.extend(tool_msgs)
                continue

            # 数量不匹配 → 按 expected_ids 顺序对齐
            logger.warning(
                "Gemini align: tool_calls=%d vs tool_responses=%d, 修补对齐",
                len(expected_ids), len(tool_msgs),
            )

            tool_by_id: dict[str, dict[str, Any]] = {}
            for tm in tool_msgs:
                tool_by_id[tm.get("tool_call_id", "")] = tm

            for tc_id in expected_ids:
                if tc_id in tool_by_id:
                    aligned.append(tool_by_id[tc_id])
                else:
                    # 补一条占位响应
                    tc_meta = next(
                        (tc for tc in tool_calls if (tc.get("id") or tc.get("function", {}).get("name", "")) == tc_id),
                        {},
                    )
                    tc_name = tc_meta.get("name") or tc_meta.get("function", {}).get("name", "unknown")
                    placeholder = {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "name": tc_name,
                        "content": "[tool response unavailable]",
                    }
                    logger.warning("Gemini align: 补齐缺失的 tool 响应 tool_call_id=%s", tc_id)
                    aligned.append(placeholder)

        return aligned

    def _rebuild_assistant_message(self, message: dict[str, Any]) -> dict[str, Any]:
        """保留 reasoning_details 的 assistant 消息重建，
        并将 Cloudsway 格式的 thought signature 注入到对应 tool_call 的 extra_content 上。
        """
        payload: dict[str, Any] = {
            k: deepcopy(v)
            for k, v in message.items()
            if k in {"role", "content", "name"}
        }
        tool_calls = message.get("tool_calls")
        if tool_calls:
            payload["tool_calls"] = [self._normalize_tool_call(tc) for tc in tool_calls]

        # 保留 reasoning_details（直接顶层或 provider_specific_fields 包装）
        rd = _extract_reasoning_details(message)
        if rd:
            payload["reasoning_details"] = deepcopy(rd)
        psf = message.get("provider_specific_fields")
        if psf:
            payload["provider_specific_fields"] = deepcopy(psf)

        # 将 Cloudsway reasoning_details 中的 thought signature 注入到 tool_call 上，
        # 确保 Gemini API 能在每个 function call 上找到 thought_signature
        self._inject_thought_signatures(payload.get("tool_calls") or [], rd)

        return payload

    def _inject_thought_signatures(
        self,
        tool_calls: list[dict[str, Any]],
        reasoning_details: list[dict[str, Any]],
    ) -> None:
        """从 reasoning_details 的 type=tool 条目中提取 signature，
        注入到缺少 extra_content.google.thought_signature 的 tool_call 上。
        """
        if not reasoning_details or not tool_calls:
            return

        # 构建 tool_call_id -> signature 映射
        sig_by_id: dict[str, str] = {}
        # 按出现顺序收集签名（无 tool_call_id 时按位置匹配）
        sig_list: list[str] = []
        for item in reasoning_details:
            if not isinstance(item, dict) or item.get("type") != "tool":
                continue
            sig = item.get("signature") or item.get("thought_signature") or ""
            if not sig:
                continue
            tc_id = item.get("tool_call_id") or ""
            if tc_id:
                sig_by_id[tc_id] = sig
            sig_list.append(sig)

        if not sig_by_id and not sig_list:
            return

        sig_idx = 0
        for tc in tool_calls:
            if _tool_call_has_thought_sig(tc):
                sig_idx += 1
                continue

            tc_id = tc.get("id") or ""
            sig = sig_by_id.get(tc_id) or (sig_list[sig_idx] if sig_idx < len(sig_list) else "")
            if sig:
                ec = tc.setdefault("extra_content", {})
                google = ec.setdefault("google", {})
                google["thought_signature"] = sig
                logger.debug("Injected thought_signature onto tool_call %s", tc_id)
            sig_idx += 1

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
        result.pop("__compressed__", None)
        result.pop("__phase2_compressed__", None)
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
        result: dict[str, Any] = {
            "id": tool_call.get("id"),
            "type": "function",
            "function": {
                "name": tool_call.get("name"),
                "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False),
            },
        }
        # 保留 thought signature（extra_content.google.thought_signature）
        if tool_call.get("extra_content"):
            result["extra_content"] = tool_call["extra_content"]
        return result

    def _normalize_tool_message(self, message: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(message)
        if "tool_call_id" not in normalized and normalized.get("name"):
            normalized["tool_call_id"] = str(normalized["name"])
        normalized.pop("provider_specific_fields", None)
        normalized.pop("__compressed__", None)
        normalized.pop("__phase2_compressed__", None)
        return normalized
