"""自定义功能页 CRUD API。

用户可以创建自定义功能页，每个页面绑定一个 agent 和若干快捷模板。
数据持久化到 {agentos_home}/custom_pages.json。
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/custom-pages", tags=["custom-pages"])


# ── 数据模型 ──

class TemplateItem(BaseModel):
    title: str
    desc: str = ""


class CustomPageCreate(BaseModel):
    name: str
    slug: str = ""
    description: str = ""
    icon: str = "Sparkles"
    agent_id: str = "office-main"
    system_prompt: str = ""
    templates: list[TemplateItem] = Field(default_factory=list)


class CustomPageUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    agent_id: str | None = None
    system_prompt: str | None = None
    templates: list[TemplateItem] | None = None


# ── 存储辅助 ──

def _storage_path(request: Request) -> Path:
    home = request.app.state.agentos_home
    return Path(home) / "custom_pages.json"


def _load_pages(request: Request) -> list[dict[str, Any]]:
    path = _storage_path(request)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_pages(request: Request, pages: list[dict[str, Any]]) -> None:
    path = _storage_path(request)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8")


def _slugify(name: str) -> str:
    import re
    slug = re.sub(r"[^\w\u4e00-\u9fff-]", "-", name.lower().strip())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or f"page-{uuid.uuid4().hex[:6]}"


# ── 路由 ──

@router.get("")
async def list_custom_pages(request: Request):
    pages = _load_pages(request)
    return {"pages": pages}


@router.post("")
async def create_custom_page(request: Request, body: CustomPageCreate):
    pages = _load_pages(request)

    slug = body.slug.strip() if body.slug else _slugify(body.name)
    if any(p["slug"] == slug for p in pages):
        slug = f"{slug}-{uuid.uuid4().hex[:4]}"

    page: dict[str, Any] = {
        "id": uuid.uuid4().hex,
        "slug": slug,
        "name": body.name,
        "description": body.description,
        "icon": body.icon,
        "agent_id": body.agent_id,
        "system_prompt": body.system_prompt,
        "templates": [t.model_dump() for t in body.templates],
        "created_at": int(time.time() * 1000),
        "updated_at": int(time.time() * 1000),
    }
    pages.append(page)
    _save_pages(request, pages)
    return page


@router.get("/{page_id}")
async def get_custom_page(request: Request, page_id: str):
    pages = _load_pages(request)
    for p in pages:
        if p["id"] == page_id or p["slug"] == page_id:
            return p
    return {"error": "not found"}, 404


@router.put("/{page_id}")
async def update_custom_page(request: Request, page_id: str, body: CustomPageUpdate):
    pages = _load_pages(request)
    for p in pages:
        if p["id"] == page_id or p["slug"] == page_id:
            if body.name is not None:
                p["name"] = body.name
            if body.description is not None:
                p["description"] = body.description
            if body.icon is not None:
                p["icon"] = body.icon
            if body.agent_id is not None:
                p["agent_id"] = body.agent_id
            if body.system_prompt is not None:
                p["system_prompt"] = body.system_prompt
            if body.templates is not None:
                p["templates"] = [t.model_dump() for t in body.templates]
            p["updated_at"] = int(time.time() * 1000)
            _save_pages(request, pages)
            return p
    return {"error": "not found"}, 404


@router.delete("/{page_id}")
async def delete_custom_page(request: Request, page_id: str):
    pages = _load_pages(request)
    new_pages = [p for p in pages if p["id"] != page_id and p["slug"] != page_id]
    if len(new_pages) == len(pages):
        return {"error": "not found"}, 404
    _save_pages(request, new_pages)
    return {"ok": True}
