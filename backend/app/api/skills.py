"""Skills API — 列表、统一搜索、市场搜索、安装/卸载/更新、启用/禁用、斜杠命令调用"""
from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
import time
from pathlib import Path

import yaml
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from app.skills.models import InstallRequest, SkillInvokeRequest
from app.skills.arg_substitutor import substitute_arguments
from app.events.types import USER_INPUT
from app.events.envelope import EventEnvelope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/skills", tags=["skills"])

BUILTIN_SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"


def _classify_skill(skill) -> str:
    """按 builtin / workspace / installed 三级分类"""
    if skill.install_info:
        return "installed"
    try:
        skill.path.resolve().relative_to(BUILTIN_SKILLS_DIR.resolve())
        return "builtin"
    except ValueError:
        return "workspace"


def _parse_skill_metadata(skill) -> dict:
    """解析 SKILL.md frontmatter 中的 metadata 字段"""
    try:
        content = (skill.path / "SKILL.md").read_text(encoding="utf-8")
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm = yaml.safe_load(parts[1])
            return (fm or {}).get("metadata", {})
    except Exception:
        pass
    return {}


# --- 已安装 Skills ---

@router.get("")
async def list_skills(request: Request):
    """获取所有已加载的 Skills（含分类、依赖状态）"""
    skill_registry = request.app.state.skill_registry
    skills = []
    for skill in skill_registry.get_all():
        category = _classify_skill(skill)
        metadata = _parse_skill_metadata(skill)
        deps = metadata.get("agentos", {}).get("requires", {}).get("bins", [])
        dep_status = {d: shutil.which(d) is not None for d in deps}

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
            "dependencies": dep_status,
            "all_deps_met": all(dep_status.values()) if dep_status else True,
        })
    return skills


# --- 统一搜索（本地 + 远程） ---

@router.get("/search")
async def unified_search(q: str, request: Request, sources: str = "all"):
    """统一搜索本地 + 远程市场"""
    skill_registry = request.app.state.skill_registry
    market_service = request.app.state.market_service
    query_lower = q.lower()
    source_list = [s.strip() for s in sources.split(",")] if sources != "all" else []

    # 1. 本地模糊匹配
    local_results = []
    if not source_list or any(s in ("local", "builtin", "workspace", "installed") for s in source_list):
        for skill in skill_registry.get_all():
            if query_lower in skill.name.lower() or query_lower in (skill.description or "").lower():
                local_results.append({
                    "id": f"local:{skill.name}",
                    "name": skill.name,
                    "description": skill.description or "",
                    "category": _classify_skill(skill),
                    "source": skill.source,
                    "version": skill.version,
                    "enabled": skill_registry.is_enabled(skill.name),
                    "installed": True,
                })

    # 2. 并发搜远程
    remote_results = []
    search_sources = []
    if not source_list or "clawhub" in source_list or sources == "all":
        search_sources.append("clawhub")
    if not source_list or "anthropic" in source_list or sources == "all":
        search_sources.append("anthropic")

    async def _search_one(src: str):
        try:
            result = await market_service.search(src, q, page=1, page_size=10)
            return [{
                "id": item.id, "name": item.name,
                "description": item.description, "category": src,
                "source": src, "version": item.version,
                "author": item.author, "downloads": item.downloads,
                "installed": skill_registry.get(item.name) is not None,
            } for item in result.items]
        except Exception as e:
            logger.warning("搜索 %s 失败: %s", src, e)
            return []

    if search_sources:
        for r in await asyncio.gather(*[_search_one(s) for s in search_sources]):
            remote_results.extend(r)

    return {
        "local_results": local_results,
        "remote_results": remote_results,
        "total_local": len(local_results),
        "total_remote": len(remote_results),
    }


# --- 市场浏览和搜索（MUST be before /{skill_name} routes） ---

@router.get("/market/browse")
async def market_browse(source: str, request: Request, page: int = 1, page_size: int = 20):
    """浏览市场 skills（无需搜索关键词，返回推荐/热门列表）"""
    market_service = request.app.state.market_service
    skill_registry = request.app.state.skill_registry
    try:
        result = await market_service.browse(source, page, page_size)
        data = result.model_dump()
        # 标记已安装状态
        for item in data.get("items", []):
            item["installed"] = skill_registry.get(item["name"]) is not None
        return data
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.warning("浏览 %s 市场失败: %s", source, e)
        raise HTTPException(status_code=502, detail={"error": str(e), "code": "NETWORK_ERROR"})


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
    skill_registry = request.app.state.skill_registry
    result = await market_service.install(
        source=body.source,
        skill_id=body.id or "",
        repo_url=body.repo_url,
    )
    if not result.get("ok"):
        code = result.get("code", "INSTALL_FAILED")
        status = 409 if code == "NAME_CONFLICT" else 400
        raise HTTPException(status_code=status, detail=result)

    # 安装成功后追加依赖状态
    skill = skill_registry.get(result.get("skill_name", ""))
    if skill:
        metadata = _parse_skill_metadata(skill)
        deps = metadata.get("agentos", {}).get("requires", {}).get("bins", [])
        dep_status = {d: shutil.which(d) is not None for d in deps}
        result["dependencies"] = dep_status
        result["all_deps_met"] = all(dep_status.values()) if dep_status else True

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
