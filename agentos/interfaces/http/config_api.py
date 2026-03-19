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
