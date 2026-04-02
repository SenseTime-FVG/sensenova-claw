from __future__ import annotations

from typing import Any, AsyncIterator

DEFAULT_LLM_TEMPERATURE = 1.0
DEFAULT_SAMPLING_EXTRA_BODY: dict[str, Any] = {
    "top_p": 0.95,
    "top_k": 20,
}


def merge_sampling_extra_body(extra_body: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = dict(DEFAULT_SAMPLING_EXTRA_BODY)
    if extra_body:
        for key, value in extra_body.items():
            if value is None:
                merged.pop(key, None)
                continue
            merged[key] = value
    return merged


class LLMProvider:
    async def call(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = DEFAULT_LLM_TEMPERATURE,
        max_tokens: int | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def stream_call(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = DEFAULT_LLM_TEMPERATURE,
        max_tokens: int | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """流式调用 LLM，逐 chunk 返回 delta。

        每个 chunk 格式:
          {"type": "delta", "content": "...", "reasoning_content": "..."}
          {"type": "tool_call_delta", "index": 0, "id": "...", "name": "...", "arguments_delta": "..."}
          {"type": "finish", "finish_reason": "stop"|"tool_calls", "usage": {...}}

        默认实现：退化为非流式调用，一次性返回完整结果。
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
        }
