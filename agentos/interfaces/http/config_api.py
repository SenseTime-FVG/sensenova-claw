"""
Config API - 按 section 读写 config.yml 中的 llm / agent / plugins
"""
from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

import yaml
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

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
    config_path = cfg._config_path

    # 读取现有 config.yml（保持其他 section 不变）
    existing: dict[str, Any] = {}
    if config_path.exists():
        try:
            raw = config_path.read_text(encoding="utf-8")
            existing = yaml.safe_load(raw) or {}
        except yaml.YAMLError:
            existing = {}

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "未提供任何更新内容")

    for section, value in updates.items():
        existing[section] = value

    # 写回 config.yml
    try:
        yaml_text = yaml.dump(
            existing,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
        config_path.write_text(yaml_text, encoding="utf-8")
    except Exception as e:
        raise HTTPException(500, f"写入配置文件失败: {e}")

    # 热更新运行时配置
    cfg.data = cfg._load_config()
    logger.info("Config sections updated and reloaded: %s", list(updates.keys()))

    # 返回更新后的 sections
    result: dict[str, Any] = {}
    for key in EDITABLE_SECTIONS:
        result[key] = deepcopy(cfg.data.get(key, {}))
    return {"status": "saved", "sections": result}
