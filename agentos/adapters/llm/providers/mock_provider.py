from __future__ import annotations

from typing import Any

from agentos.adapters.llm.base import LLMProvider


class MockProvider(LLMProvider):
    async def call(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _ = (model, temperature, max_tokens, extra_body)
        last = messages[-1] if messages else {"content": ""}
        content = str(last.get("content", ""))

        # mock规则：若用户询问英超冠亚军且可用工具，则先触发工具调用。
        if "英超" in content and "冠亚军" in content and tools:
            return {
                "content": "我将先搜索近三年的英超冠亚军信息。",
                "tool_calls": [
                    {
                        "id": "mock_tool_1",
                        "name": "serper_search",
                        "arguments": {"q": "英超 最近3年 冠军 亚军", "page": 1},
                    }
                ],
                "finish_reason": "tool_calls",
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            }

        # 若最后一条是工具结果，则返回整理后的答案。
        if last.get("role") == "tool":
            return {
                "content": "根据工具返回结果，已整理最近3年的英超冠亚军信息。",
                "tool_calls": [],
                "finish_reason": "stop",
                "usage": {"prompt_tokens": 20, "completion_tokens": 30, "total_tokens": 50},
            }

        return {
            "content": f"这是 mock 回复：{content}",
            "tool_calls": [],
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 8, "completion_tokens": 12, "total_tokens": 20},
        }
