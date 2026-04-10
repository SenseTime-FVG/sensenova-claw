from __future__ import annotations

from typing import Any

from sensenova_claw.adapters.llm.base import DEFAULT_LLM_TEMPERATURE, LLMProvider


class MockProvider(LLMProvider):
    async def call(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = DEFAULT_LLM_TEMPERATURE,
        max_tokens: int | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _ = (model, temperature, max_tokens, extra_body)
        last = messages[-1] if messages else {"content": ""}
        content = str(last.get("content", ""))

        mcp_tool_name = ""
        if tools:
            for tool in tools:
                name = str(tool.get("name", ""))
                if name.startswith("mcp__"):
                    mcp_tool_name = name
                    break

        if ("MCP" in content or "mcp" in content) and mcp_tool_name:
            return {
                "content": "我将调用 MCP 工具完成这次请求。",
                "tool_calls": [
                    {
                        "id": "mock_mcp_tool_1",
                        "name": mcp_tool_name,
                        "arguments": {"text": "hello-from-mock"},
                    }
                ],
                "finish_reason": "tool_calls",
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            }

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
            tool_content = str(last.get("content", ""))
            if "MCP_ECHO:" in tool_content:
                return {
                    "content": f"根据 MCP 工具结果，收到 {tool_content}",
                    "tool_calls": [],
                    "finish_reason": "stop",
                    "usage": {"prompt_tokens": 20, "completion_tokens": 30, "total_tokens": 50},
                }
            return {
                "content": "根据工具返回结果，已整理最近3年的英超冠亚军信息。",
                "tool_calls": [],
                "finish_reason": "stop",
                "usage": {"prompt_tokens": 20, "completion_tokens": 30, "total_tokens": 50},
            }

        return {
            "content": (
                "当前没有可用的 LLM，请先前往「配置」页面添加至少一个可用的大模型，"
                "然后联系运维工程师完成其余配置。"
            ),
            "tool_calls": [],
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 8, "completion_tokens": 12, "total_tokens": 20},
        }
