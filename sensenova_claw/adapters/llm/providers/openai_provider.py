from __future__ import annotations

import json
import logging
import platform
import uuid
from typing import Any, AsyncIterator

import httpx
from openai import AsyncOpenAI

from sensenova_claw.platform.config.config import config
from sensenova_claw.platform.auth.openai_codex_oauth import resolve_openai_codex_access_token
from sensenova_claw.adapters.llm.base import (
    DEFAULT_LLM_TEMPERATURE,
    LLMProvider,
    merge_sampling_extra_body,
)

logger = logging.getLogger(__name__)


OPENAI_CODEX_BACKEND_API_BASE_URL = "https://chatgpt.com/backend-api"


class OpenAIProvider(LLMProvider):
    def __init__(self, provider_id: str = "openai", source_type: str | None = None):
        provider_cfg = config.get(f"llm.providers.{provider_id}", {})
        self.provider_id = provider_id
        self.source_type = source_type or str(provider_cfg.get("source_type", "openai") or "openai")
        self.timeout = int(provider_cfg.get("timeout", 60) or 60)
        if self.source_type == "openai-codex-oauth":
            self.client = None
            return
        self.client = AsyncOpenAI(
            api_key=provider_cfg.get("api_key"),
            base_url=provider_cfg.get("base_url") or None,
            timeout=self.timeout,
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
        if self.source_type == "openai-codex-oauth":
            return await self._call_openai_codex_responses(
                model=model,
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
            )

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
        if self.source_type == "openai-codex-oauth":
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
            yield {
                "type": "finish",
                "finish_reason": result.get("finish_reason", "stop"),
                "usage": result.get("usage", {}),
                "tool_calls": result.get("tool_calls", []),
            }
            return

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

    def _openai_codex_responses_url(self) -> str:
        return f"{OPENAI_CODEX_BACKEND_API_BASE_URL}/codex/responses"

    def _build_openai_codex_headers(self, access_token: str, session_id: str | None = None) -> dict[str, str]:
        account_id = self._extract_openai_codex_account_id(access_token)
        request_id = session_id or str(uuid.uuid4())
        headers = {
            "Authorization": f"Bearer {access_token}",
            "chatgpt-account-id": account_id,
            "originator": "pi",
            "User-Agent": f"pi ({platform.system().lower()} {platform.release()}; {platform.machine()})",
            "OpenAI-Beta": "responses=experimental",
            "accept": "text/event-stream",
            "content-type": "application/json",
            "x-client-request-id": request_id,
        }
        if session_id:
            headers["session_id"] = session_id
        return headers

    def _extract_openai_codex_account_id(self, access_token: str) -> str:
        payload = self._decode_jwt_payload(access_token)
        auth = payload.get("https://api.openai.com/auth")
        if isinstance(auth, dict):
            for key in ("chatgpt_account_id", "id"):
                value = auth.get(key)
                if isinstance(value, str) and value:
                    return value
        raise RuntimeError("OpenAI-Codex-OAuth access token 缺少 chatgpt account id，请重新 Login")

    def _decode_jwt_payload(self, token: str) -> dict[str, Any]:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        import base64
        import binascii

        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        try:
            decoded = base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8")
            value = json.loads(decoded)
        except (UnicodeDecodeError, ValueError, binascii.Error):
            return {}
        return value if isinstance(value, dict) else {}

    async def _call_openai_codex_responses(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        req: dict[str, Any] = {
            "model": model,
            "input": self._normalize_responses_input(messages),
            "stream": True,
            "store": False,
            "text": {"verbosity": "medium"},
            "include": ["reasoning.encrypted_content"],
            "tool_choice": "auto",
            "parallel_tool_calls": True,
        }
        if temperature is not None:
            req["temperature"] = temperature
        if max_tokens:
            req["max_output_tokens"] = max_tokens
        if tools:
            req["tools"] = [self._normalize_responses_tool(tool) for tool in tools]

        response = await self._post_openai_codex_responses(req)
        tool_calls = response["tool_calls"]
        return {
            "content": response["content"],
            "tool_calls": tool_calls,
            "finish_reason": "tool_calls" if tool_calls else response["finish_reason"],
            "usage": response["usage"],
        }

    async def _post_openai_codex_responses(self, payload: dict[str, Any]) -> dict[str, Any]:
        access_token = resolve_openai_codex_access_token()
        content_parts: list[str] = []
        usage: dict[str, int] = {}
        tool_calls: list[dict[str, Any]] = []
        finish_reason = "stop"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                self._openai_codex_responses_url(),
                headers=self._build_openai_codex_headers(access_token),
                json=payload,
            ) as response:
                if not response.is_success:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    raise RuntimeError(self._format_openai_codex_http_error(response.status_code, body))
                async for event in self._iter_openai_codex_sse_events(response):
                    event_type = str(event.get("type") or "")
                    if event_type == "response.output_text.delta" and isinstance(event.get("delta"), str):
                        content_parts.append(event["delta"])
                    elif event_type == "response.completed":
                        finish_reason = "stop"
                        response_obj = event.get("response")
                        if isinstance(response_obj, dict):
                            usage = self._extract_responses_usage_dict(response_obj.get("usage"))
                    elif event_type in {"response.done", "response.incomplete"}:
                        response_obj = event.get("response")
                        if isinstance(response_obj, dict):
                            usage = self._extract_responses_usage_dict(response_obj.get("usage"))
                    elif event_type == "response.failed":
                        response_obj = event.get("response")
                        if isinstance(response_obj, dict):
                            error = response_obj.get("error")
                            if isinstance(error, dict) and isinstance(error.get("message"), str):
                                raise RuntimeError(error["message"])
                        raise RuntimeError("OpenAI-Codex-OAuth response failed")
                    elif event_type == "error":
                        message = event.get("message")
                        raise RuntimeError(str(message or event))
                    elif event_type == "response.output_item.done":
                        item = event.get("item")
                        if isinstance(item, dict) and item.get("type") == "function_call":
                            tool_calls.append(self._normalize_responses_function_call(item))

        return {
            "content": "".join(content_parts),
            "tool_calls": tool_calls,
            "finish_reason": finish_reason,
            "usage": usage,
        }

    async def _iter_openai_codex_sse_events(self, response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
        data_lines: list[str] = []
        async for line in response.aiter_lines():
            if not line:
                if data_lines:
                    data = "\n".join(data_lines).strip()
                    data_lines = []
                    if data and data != "[DONE]":
                        try:
                            parsed = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(parsed, dict):
                            yield parsed
                continue
            if line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if data_lines:
            data = "\n".join(data_lines).strip()
            if data and data != "[DONE]":
                try:
                    parsed = json.loads(data)
                except json.JSONDecodeError:
                    return
                if isinstance(parsed, dict):
                    yield parsed

    def _format_openai_codex_http_error(self, status_code: int, body: str) -> str:
        stripped = body.strip()
        if stripped.startswith("<html") or "<html" in stripped[:200].lower():
            return (
                f"OpenAI-Codex-OAuth HTTP 请求被 chatgpt.com 拦截（HTTP {status_code}）。"
                "请确认使用的是 /backend-api/codex/responses transport，并重新 Login 后再试。"
            )
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return stripped or f"OpenAI-Codex-OAuth HTTP 请求失败（HTTP {status_code}）"
        error = parsed.get("error") if isinstance(parsed, dict) else None
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"]
        return stripped or f"OpenAI-Codex-OAuth HTTP 请求失败（HTTP {status_code}）"

    def _extract_responses_usage_dict(self, usage: Any) -> dict[str, int]:
        if not isinstance(usage, dict):
            return {}
        input_tokens = usage.get("input_tokens") or 0
        output_tokens = usage.get("output_tokens") or 0
        total_tokens = usage.get("total_tokens") or (int(input_tokens) + int(output_tokens))
        return {
            "prompt_tokens": int(input_tokens),
            "completion_tokens": int(output_tokens),
            "total_tokens": int(total_tokens),
        }

    def _normalize_responses_function_call(self, item: dict[str, Any]) -> dict[str, Any]:
        arguments = item.get("arguments")
        try:
            parsed_arguments = json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
        except json.JSONDecodeError:
            parsed_arguments = arguments
        return {
            "id": str(item.get("call_id") or item.get("id") or ""),
            "name": str(item.get("name") or ""),
            "arguments": parsed_arguments,
        }

    def _normalize_responses_input(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for message in self._normalize_messages(messages):
            role = str(message.get("role") or "user")
            if role == "tool":
                normalized.append({
                    "role": "user",
                    "content": self._stringify_responses_content(message.get("content")),
                })
                continue
            if role not in {"user", "assistant", "system", "developer"}:
                role = "user"
            normalized.append({
                "role": role,
                "content": self._normalize_responses_content(message.get("content")),
            })
        return normalized

    def _normalize_responses_content(self, content: Any) -> Any:
        if not isinstance(content, list):
            return content if isinstance(content, str) else self._stringify_responses_content(content)

        blocks: list[dict[str, Any]] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type in {"text", "input_text"} and isinstance(item.get("text"), str):
                blocks.append({"type": "input_text", "text": item["text"]})
            elif item_type in {"image_url", "input_image"}:
                image_url = item.get("image_url")
                if isinstance(image_url, dict):
                    image_url = image_url.get("url")
                if isinstance(image_url, str) and image_url:
                    blocks.append({"type": "input_image", "image_url": image_url, "detail": "auto"})
        return blocks if blocks else ""

    def _stringify_responses_content(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if content is None:
            return ""
        return json.dumps(content, ensure_ascii=False)

    def _normalize_responses_tool(self, tool: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "function",
            "name": str(tool.get("name") or ""),
            "description": str(tool.get("description") or ""),
            "parameters": tool.get("parameters") if isinstance(tool.get("parameters"), dict) else {},
            "strict": False,
        }

    def _extract_responses_text(self, response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text:
            return output_text

        parts: list[str] = []
        for item in getattr(response, "output", []) or []:
            content = getattr(item, "content", None)
            if content is None and isinstance(item, dict):
                content = item.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                text = getattr(block, "text", None)
                if text is None and isinstance(block, dict):
                    text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)

    def _extract_responses_tool_calls(self, response: Any) -> list[dict[str, Any]]:
        tool_calls: list[dict[str, Any]] = []
        for item in getattr(response, "output", []) or []:
            item_type = getattr(item, "type", None)
            if item_type is None and isinstance(item, dict):
                item_type = item.get("type")
            if item_type != "function_call":
                continue
            name = getattr(item, "name", None)
            if name is None and isinstance(item, dict):
                name = item.get("name")
            arguments = getattr(item, "arguments", None)
            if arguments is None and isinstance(item, dict):
                arguments = item.get("arguments")
            try:
                parsed_arguments = json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
            except json.JSONDecodeError:
                parsed_arguments = arguments
            call_id = getattr(item, "call_id", None) or getattr(item, "id", None)
            if call_id is None and isinstance(item, dict):
                call_id = item.get("call_id") or item.get("id")
            tool_calls.append({
                "id": str(call_id or ""),
                "name": str(name or ""),
                "arguments": parsed_arguments,
            })
        return tool_calls

    def _extract_responses_finish_reason(self, response: Any) -> str:
        status = getattr(response, "status", None)
        if status == "completed":
            return "stop"
        if isinstance(status, str) and status:
            return status
        return "stop"

    def _extract_responses_usage(self, response: Any) -> dict[str, int]:
        usage = getattr(response, "usage", None)
        if not usage:
            return {}
        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)
        total_tokens = getattr(usage, "total_tokens", None)
        return {
            "prompt_tokens": int(input_tokens or 0),
            "completion_tokens": int(output_tokens or 0),
            "total_tokens": int(total_tokens or ((input_tokens or 0) + (output_tokens or 0))),
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
            if role == "user" and message.get("attachments"):
                normalized.append(self._normalize_user_message(message))
                continue
            if role == "assistant" and isinstance(message.get("tool_calls"), list):
                normalized.append(self._normalize_assistant_message(message, has_thinking))
                continue
            if role == "tool":
                normalized.append(self._normalize_tool_message(message))
                continue
            normalized.append(dict(message))
        return self._align_tool_call_responses(normalized)

    def _normalize_user_message(self, message: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(message)
        attachments = normalized.pop("attachments", []) or []
        blocks: list[dict[str, Any]] = []

        content = normalized.get("content", "")
        if isinstance(content, str) and content:
            blocks.append({"type": "text", "text": content})

        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            if str(attachment.get("kind") or "") != "image":
                continue
            mime_type = str(attachment.get("mime_type") or "").strip()
            data = str(attachment.get("data") or "").strip()
            if not mime_type or not data:
                continue
            blocks.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{data}"},
            })

        normalized["content"] = blocks or [{"type": "text", "text": ""}]
        return normalized

    def _align_tool_call_responses(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """确保每个 assistant tool_calls 之后都有完整的 tool 响应。

        部分 OpenAI 兼容网关会严格校验：
        - assistant 含 tool_calls 后，后续必须紧跟对应的 tool 消息
        - 不允许出现没有前置 tool_calls 的孤儿 tool 消息
        因此这里在请求前统一补齐/清理历史，避免旧会话残留导致 400。
        """
        aligned: list[dict[str, Any]] = []
        index = 0

        while index < len(messages):
            message = messages[index]
            tool_calls = message.get("tool_calls") if message.get("role") == "assistant" else None

            if not tool_calls:
                if self._is_orphan_tool_message(message, aligned):
                    logger.warning(
                        "OpenAI align: 跳过孤儿 tool 消息 tool_call_id=%s",
                        message.get("tool_call_id"),
                    )
                    index += 1
                    continue
                aligned.append(message)
                index += 1
                continue

            expected_ids = [
                str(tc.get("id") or tc.get("function", {}).get("name", "") or "")
                for tc in tool_calls
            ]
            aligned.append(message)
            index += 1

            tool_messages: list[dict[str, Any]] = []
            while index < len(messages) and messages[index].get("role") == "tool":
                tool_messages.append(messages[index])
                index += 1

            if len(tool_messages) == len(expected_ids) and all(
                tool_msg.get("tool_call_id") in expected_ids for tool_msg in tool_messages
            ):
                aligned.extend(tool_messages)
                continue

            logger.warning(
                "OpenAI align: tool_calls=%d vs tool_responses=%d, 修补对齐",
                len(expected_ids),
                len(tool_messages),
            )
            tool_by_id = {
                str(tool_msg.get("tool_call_id") or ""): tool_msg
                for tool_msg in tool_messages
                if str(tool_msg.get("tool_call_id") or "")
            }

            for tool_call in tool_calls:
                tool_call_id = str(
                    tool_call.get("id") or tool_call.get("function", {}).get("name", "") or ""
                )
                if tool_call_id in tool_by_id:
                    aligned.append(tool_by_id[tool_call_id])
                    continue

                tool_name = (
                    tool_call.get("name")
                    or tool_call.get("function", {}).get("name")
                    or "unknown"
                )
                logger.warning("OpenAI align: 补齐缺失的 tool 响应 tool_call_id=%s", tool_call_id)
                aligned.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": tool_name,
                    "content": "[tool response unavailable]",
                })

        return aligned

    def _is_orphan_tool_message(
        self,
        message: dict[str, Any],
        aligned: list[dict[str, Any]],
    ) -> bool:
        if message.get("role") != "tool":
            return False
        if not aligned:
            return True
        if aligned[-1].get("role") == "assistant" and aligned[-1].get("tool_calls"):
            return False

        for previous in reversed(aligned):
            if previous.get("role") == "assistant" and previous.get("tool_calls"):
                return False
            if previous.get("role") in ("user", "system"):
                break
        return True

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
        normalized.pop("attachments", None)
        return normalized
