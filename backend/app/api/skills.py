"""Skills API — 列表、市场搜索、安装/卸载/更新、启用/禁用、斜杠命令调用"""
from __future__ import annotations

import uuid
import time
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from app.skills.models import InstallRequest, SkillInvokeRequest
from app.skills.arg_substitutor import substitute_arguments
from app.events.types import USER_INPUT
from app.events.envelope import EventEnvelope

router = APIRouter(prefix="/api/skills", tags=["skills"])


# --- 已安装 Skills ---

@router.get("")
async def list_skills(request: Request):
    """获取所有已加载的 Skills（扩展版，含 source/version/update 信息）"""
    skill_registry = request.app.state.skill_registry
    skills = []
    for skill in skill_registry.get_all():
        info = skill.install_info
        if info:
            category = "installed"
        elif skill.source == "local":
            category = "local"
        else:
            category = "builtin"

        skills.append({
            "id": f"skill-{skill.name}",
            "name": skill.name,
            "description": skill.description or "",
            "category": category,
            "enabled": skill_registry.is_enabled(skill.name),
            "path": str(skill.path),
            "source": skill.source,
            "version": skill.version,
            "has_update": False,
            "update_version": None,
        })
    return skills


# --- 市场搜索（MUST be before /{skill_name} routes） ---

@router.get("/market/search")
async def market_search(source: str, q: str, request: Request, page: int = 1, page_size: int = 20):
    """搜索市场 skills"""
    market_service = request.app.state.market_service
    try:
        result = await market_service.search(source, q, page, page_size)
        return result.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail={"error": str(e), "code": "NETWORK_ERROR"})


@router.get("/market/detail")
async def market_detail(source: str, id: str, request: Request):
    """获取市场 skill 详情"""
    market_service = request.app.state.market_service
    try:
        detail = await market_service.get_detail(source, id)
        return detail.model_dump()
    except Exception as e:
        raise HTTPException(status_code=502, detail={"error": str(e), "code": "NETWORK_ERROR"})


# --- 安装 ---

@router.post("/install")
async def install_skill(body: InstallRequest, request: Request):
    """从市场安装 skill"""
    market_service = request.app.state.market_service
    result = await market_service.install(
        source=body.source,
        skill_id=body.id or "",
        repo_url=body.repo_url,
    )
    if not result.get("ok"):
        code = result.get("code", "INSTALL_FAILED")
        status = 409 if code == "NAME_CONFLICT" else 400
        raise HTTPException(status_code=status, detail=result)
    return result


# --- 检查更新 ---

@router.post("/check-updates")
async def check_updates(request: Request):
    """检查所有已安装 skill 的更新"""
    market_service = request.app.state.market_service
    updates = await market_service.check_updates()
    return {"updates": updates}


# --- 启用/禁用 ---

class ToggleRequest(BaseModel):
    enabled: bool

@router.patch("/{skill_name}")
async def toggle_skill(skill_name: str, body: ToggleRequest, request: Request):
    """启用/禁用 skill"""
    registry = request.app.state.skill_registry
    registry.set_enabled(skill_name, body.enabled)
    if body.enabled:
        config = request.app.state.config.data if hasattr(request.app.state.config, 'data') else {}
        registry.load_skills(config)
    return {"ok": True, "skill_name": skill_name, "enabled": body.enabled}


# --- 卸载 ---

@router.delete("/{skill_name}")
async def uninstall_skill(skill_name: str, request: Request):
    """卸载已安装的 skill"""
    market_service = request.app.state.market_service
    result = await market_service.uninstall(skill_name)
    if not result.get("ok"):
        status = 403 if result.get("code") == "PERMISSION_DENIED" else 404
        raise HTTPException(status_code=status, detail=result)
    return result


# --- 更新 ---

@router.post("/{skill_name}/update")
async def update_skill(skill_name: str, request: Request):
    """更新已安装的 skill"""
    market_service = request.app.state.market_service
    result = await market_service.update(skill_name)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return result


# --- 斜杠命令调用 ---

invoke_router = APIRouter(prefix="/api/sessions", tags=["skills"])

@invoke_router.post("/{session_id}/skill-invoke")
async def invoke_skill(session_id: str, body: SkillInvokeRequest, request: Request):
    """用户显式调用 skill（斜杠命令）"""
    registry = request.app.state.skill_registry
    skill = registry.get(body.skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{body.skill_name}' not found")

    # 参数替换
    rendered = substitute_arguments(skill.body, body.arguments)

    # 发布 user.input 事件
    services = request.app.state.services
    event = EventEnvelope(
        type=USER_INPUT,
        session_id=session_id,
        source="api",
        payload={
            "content": rendered,
            "type": "skill_invoke",
            "skill_name": body.skill_name,
            "original_input": f"/{body.skill_name} {body.arguments}".strip(),
        },
    )
    await services.publisher.publish(event)
    return {"ok": True, "session_id": session_id, "skill_name": body.skill_name}
