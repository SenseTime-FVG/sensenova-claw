"""
Skills API - 从真实 SkillRegistry 读取已加载的 skills
"""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("")
async def list_skills(request: Request):
    """获取所有已加载的 Skills"""
    skill_registry = request.app.state.skill_registry
    skills = []
    for skill in skill_registry.get_all():
        skills.append({
            "id": f"skill-{skill.name}",
            "name": skill.name,
            "description": skill.description or "",
            "category": "builtin",
            "enabled": True,
            "path": str(skill.path),
        })
    return skills
