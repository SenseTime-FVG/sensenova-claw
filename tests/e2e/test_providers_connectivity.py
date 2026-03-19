"""
各 LLM 厂商 API 连通性测试。

直接从项目根目录 config.yml 读取真实 key，绕过模块级 config 单例，
逐一验证每个 provider 能否完成基本对话和 function calling。
跳过未配置 api_key 的 provider。

运行方式:
    python3 -m pytest tests/e2e/test_providers_connectivity.py -v
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest
import yaml
from openai import AsyncOpenAI, APIStatusError

logger = logging.getLogger(__name__)

# 项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config.yml"

# 某些模型不支持自定义 temperature（如 kimi-k2.5 只允许 temperature=1）
_FIXED_TEMPERATURE_MODELS = {"kimi-k2.5"}

# 思考类模型可能需要更大 max_tokens 才能输出 content
_THINKING_MODELS = {"GLM-5", "MiniMax-M2.7-highspeed", "qwen3.5-plus", "kimi-k2.5", "step-3.5-flash"}


def _load_providers_config() -> dict[str, Any]:
    """从项目根目录 config.yml 直接读取 llm.providers 配置"""
    if not _CONFIG_PATH.exists():
        return {}
    with _CONFIG_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("llm", {}).get("providers", {})


_PROVIDERS_CFG = _load_providers_config()


def _has_api_key(provider_key: str) -> bool:
    """检查 provider 是否配置了有效的 api_key"""
    cfg = _PROVIDERS_CFG.get(provider_key, {})
    key = cfg.get("api_key", "")
    return bool(key) and not key.startswith("${")


def _make_client(provider_key: str) -> AsyncOpenAI:
    """根据 provider 配置创建 AsyncOpenAI 客户端"""
    cfg = _PROVIDERS_CFG.get(provider_key, {})
    return AsyncOpenAI(
        api_key=cfg.get("api_key"),
        base_url=cfg.get("base_url") or None,
        timeout=cfg.get("timeout", 60),
    )


async def _chat(
    client: AsyncOpenAI,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 100,
) -> dict[str, Any]:
    """发起一次 chat completion 请求，返回标准化结果"""
    # 思考类模型需要更大 max_tokens
    if model in _THINKING_MODELS and max_tokens < 1000:
        max_tokens = 1000

    req: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }

    # 某些模型不支持自定义 temperature
    if model not in _FIXED_TEMPERATURE_MODELS:
        req["temperature"] = 0.1

    if tools:
        req["tools"] = [{"type": "function", "function": t} for t in tools]

    response = await client.chat.completions.create(**req)
    choice = response.choices[0]
    message = choice.message

    tool_calls: list[dict[str, Any]] = []
    if message.tool_calls:
        for tc in message.tool_calls:
            args = tc.function.arguments
            parsed = json.loads(args) if isinstance(args, str) else args
            tool_calls.append({
                "id": tc.id,
                "name": tc.function.name,
                "arguments": parsed,
            })

    return {
        "content": message.content or "",
        "tool_calls": tool_calls,
        "finish_reason": "tool_calls" if tool_calls else (choice.finish_reason or "stop"),
        "usage": {
            "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
            "completion_tokens": getattr(response.usage, "completion_tokens", 0),
            "total_tokens": getattr(response.usage, "total_tokens", 0),
        },
    }


# ════════════════════════════════════════════════════
# 基本对话测试
# ════════════════════════════════════════════════════

CHAT_CASES: list[tuple[str, str, str]] = [
    ("kimi",     "kimi-k2.5",                        "Kimi (Moonshot)"),
    ("glm",      "GLM-5",                            "GLM (智谱)"),
    ("minimax",  "MiniMax-M2.7-highspeed",           "Minimax"),
    ("qwen",     "qwen3.5-plus",                     "Qwen (通义千问)"),
    ("deepseek", "deepseek-chat",                    "Deepseek"),
    ("step",     "step-3.5-flash",                   "Step (阶跃星辰)"),
    ("gemini",   "MaaS_Ge_3.1_pro_preview_20260219", "Gemini (Cloudsway)"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_key, model_id, desc",
    CHAT_CASES,
    ids=[c[2] for c in CHAT_CASES],
)
async def test_chat_completion(
    provider_key: str, model_id: str, desc: str
) -> None:
    """验证各厂商的基本对话能力"""
    if not _has_api_key(provider_key):
        pytest.skip(f"{desc}: 未配置 api_key，跳过")

    client = _make_client(provider_key)
    messages = [{"role": "user", "content": "请用一句话回答：1+1等于几？"}]

    try:
        result = await _chat(client, model_id, messages)
    except APIStatusError as e:
        if e.status_code == 402:
            pytest.skip(f"{desc}: 余额不足(402)，跳过")
        raise

    logger.info("[%s] 响应: %s", desc, result["content"][:200])
    print(f"\n  [{desc}] ✓ 响应: {result['content'][:100]}")

    assert result.get("content"), f"{desc}: 应返回非空 content"
    assert result.get("finish_reason") in ("stop", "length"), (
        f"{desc}: finish_reason={result.get('finish_reason')}"
    )
    assert result.get("usage", {}).get("total_tokens", 0) > 0, (
        f"{desc}: total_tokens 应大于 0"
    )


# ════════════════════════════════════════════════════
# 工具调用测试（function calling 兼容性）
# ════════════════════════════════════════════════════

TOOL_CALL_CASES: list[tuple[str, str, str]] = [
    ("qwen",     "qwen3.5-plus",           "Qwen (通义千问)"),
    ("deepseek", "deepseek-chat",          "Deepseek"),
    ("glm",      "GLM-5",                  "GLM (智谱)"),
    ("kimi",     "kimi-k2.5",              "Kimi (Moonshot)"),
    ("minimax",  "MiniMax-M2.7-highspeed", "Minimax"),
    ("step",     "step-3.5-flash",         "Step (阶跃星辰)"),
]

DUMMY_TOOL = {
    "name": "get_weather",
    "description": "获取指定城市的天气信息",
    "parameters": {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "城市名称"},
        },
        "required": ["city"],
    },
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_key, model_id, desc",
    TOOL_CALL_CASES,
    ids=[c[2] for c in TOOL_CALL_CASES],
)
async def test_tool_call_compatibility(
    provider_key: str, model_id: str, desc: str
) -> None:
    """验证厂商的 function calling 能力"""
    if not _has_api_key(provider_key):
        pytest.skip(f"{desc}: 未配置 api_key，跳过")

    client = _make_client(provider_key)
    messages = [{"role": "user", "content": "北京今天天气怎么样？"}]

    try:
        result = await _chat(client, model_id, messages, tools=[DUMMY_TOOL], max_tokens=500)
    except APIStatusError as e:
        if e.status_code == 402:
            pytest.skip(f"{desc}: 余额不足(402)，跳过")
        raise

    print(f"\n  [{desc}] tool_calls: {result.get('tool_calls')}")

    tool_calls = result.get("tool_calls", [])
    assert len(tool_calls) > 0, f"{desc}: 应返回至少一个 tool_call"
    assert tool_calls[0].get("name") == "get_weather", (
        f"{desc}: 应调用 get_weather，实际: {tool_calls[0].get('name')}"
    )
    args = tool_calls[0].get("arguments", {})
    assert "city" in args or "北京" in str(args), (
        f"{desc}: tool_call 参数应包含 city，实际: {args}"
    )
