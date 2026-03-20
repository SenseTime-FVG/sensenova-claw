"""
Config API - 按 section 读写 config.yml 中的 llm / agent / plugins
"""
from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from agentos.interfaces.http.config_store import persist_section_updates
from agentos.platform.config.llm_presets import check_llm_configured, LLM_PROVIDER_CATEGORIES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])

EDITABLE_SECTIONS = ("llm", "agent", "plugins")


class SectionsUpdateBody(BaseModel):
    llm: dict[str, Any] | None = None
    agent: dict[str, Any] | None = None
    plugins: dict[str, Any] | None = None


class TestLLMBody(BaseModel):
    provider: str       # 'openai' | 'anthropic' | 'gemini'
    api_key: str
    base_url: str = ""
    model_id: str


@router.get("/sections")
async def get_config_sections(request: Request):
    """返回 llm / agent / plugins 三个 section 的当前值"""
    cfg = request.app.state.config
    result: dict[str, Any] = {}
    for key in EDITABLE_SECTIONS:
        result[key] = deepcopy(cfg.data.get(key, {}))
    return result


@router.put("/sections")
async def update_config_sections(body: SectionsUpdateBody, request: Request):
    """更新指定 section 并持久化到 config.yml，同时热更新运行时配置"""
    cfg = request.app.state.config

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "未提供任何更新内容")

    try:
        data = persist_section_updates(cfg, updates)
    except Exception as e:
        raise HTTPException(500, f"写入配置文件失败: {e}")

    logger.info("Config sections updated and reloaded: %s", list(updates.keys()))

    # 返回更新后的 sections
    result: dict[str, Any] = {}
    for key in EDITABLE_SECTIONS:
        result[key] = deepcopy(data.get(key, {}))
    return {"status": "saved", "sections": result}


@router.get("/llm-status")
async def get_llm_status(request: Request):
    """检测当前配置中是否至少有一个 LLM 提供商已配置有效 API key"""
    cfg = request.app.state.config
    is_configured, providers = check_llm_configured(cfg.data)
    return {"configured": is_configured, "providers": providers}


@router.get("/llm-presets")
async def get_llm_presets():
    """返回所有 LLM 提供商预设分类列表，供前端展示使用"""
    return {"categories": LLM_PROVIDER_CATEGORIES}


@router.post("/test-llm")
async def test_llm_connection(body: TestLLMBody):
    """用临时配置测试 LLM 连通性，发送一个简单请求验证 API key 和模型是否可用"""
    provider = body.provider
    try:
        if provider in ("openai", "anthropic", "gemini"):
            result = await _test_openai_compatible(
                api_key=body.api_key,
                base_url=body.base_url,
                model_id=body.model_id,
            ) if provider == "openai" else (
                await _test_anthropic(
                    api_key=body.api_key,
                    base_url=body.base_url,
                    model_id=body.model_id,
                ) if provider == "anthropic" else
                await _test_gemini(
                    api_key=body.api_key,
                    base_url=body.base_url,
                    model_id=body.model_id,
                )
            )
            return {"success": True, **result}
        else:
            # 未知 provider 类型，尝试 OpenAI 兼容方式
            result = await _test_openai_compatible(
                api_key=body.api_key,
                base_url=body.base_url,
                model_id=body.model_id,
            )
            return {"success": True, **result}
    except Exception as e:
        logger.warning("LLM test failed: %s", e)
        return {"success": False, "error": str(e)}


async def _test_openai_compatible(api_key: str, base_url: str, model_id: str) -> dict:
    """通过 OpenAI SDK 测试连通性"""
    from openai import AsyncOpenAI
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url or None,
        timeout=15,
    )
    response = await client.chat.completions.create(
        model=model_id,
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=5,
    )
    return {"model": response.model, "message": "连接成功"}


async def _test_anthropic(api_key: str, base_url: str, model_id: str) -> dict:
    """通过 Anthropic SDK 测试连通性"""
    import anthropic
    client = anthropic.AsyncAnthropic(
        api_key=api_key,
        base_url=base_url or None,
        timeout=15,
    )
    response = await client.messages.create(
        model=model_id,
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=5,
    )
    return {"model": response.model, "message": "连接成功"}


async def _test_gemini(api_key: str, base_url: str, model_id: str) -> dict:
    """通过 OpenAI 兼容方式测试 Gemini"""
    from openai import AsyncOpenAI
    gemini_base = base_url or "https://generativelanguage.googleapis.com/v1beta/openai"
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=gemini_base,
        timeout=15,
    )
    response = await client.chat.completions.create(
        model=model_id,
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=5,
    )
    return {"model": response.model, "message": "连接成功"}
