"""自定义功能页 / mini-app API。

当前 custom page 已升级为带工作区、专属 Agent 和生成任务状态的 mini-app 页面。
原有列表/详情接口保持兼容。
"""

from __future__ import annotations

from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from sensenova_claw.capabilities.miniapps.service import MiniAppService

router = APIRouter(prefix="/api/custom-pages", tags=["custom-pages"])


class TemplateItem(BaseModel):
    title: str
    desc: str = ""


class CustomPageCreate(BaseModel):
    name: str
    slug: str = ""
    description: str = ""
    icon: str = "Sparkles"
    agent_id: str = "default"
    system_prompt: str = ""
    templates: list[TemplateItem] = Field(default_factory=list)
    create_dedicated_agent: bool = True
    workspace_mode: Literal["scratch", "reuse"] = "scratch"
    source_project_path: str = ""
    builder_type: Literal["builtin", "acp"] = "builtin"
    generation_prompt: str = ""


class CustomPageUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    system_prompt: str | None = None
    templates: list[TemplateItem] | None = None
    workspace_mode: Literal["scratch", "reuse"] | None = None
    source_project_path: str | None = None
    builder_type: Literal["builtin", "acp"] | None = None
    generation_prompt: str | None = None


class GenerateRequest(BaseModel):
    prompt: str = ""


class MiniAppInteractionRequest(BaseModel):
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)
    message: str = ""
    session_id: str = ""
    refresh_mode: Literal["none", "background", "immediate"] = "none"


class MiniAppActionRequest(BaseModel):
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)
    message: str = ""
    session_id: str = ""
    target: Literal["local", "server", "agent"] = "agent"
    refresh_mode: Literal["none", "background", "immediate"] = "none"


def _get_service(request: Request) -> MiniAppService:
    service = getattr(request.app.state, "custom_page_service", None)
    if service is not None:
        return service

    gateway = None
    services = getattr(request.app.state, "services", None)
    if services is not None:
        gateway = getattr(services, "gateway", None)

    sensenova_claw_home = getattr(request.app.state, "sensenova_claw_home", "")
    config = getattr(request.app.state, "config", None)
    agent_registry = getattr(request.app.state, "agent_registry", None)
    if not config or not agent_registry:
        raise RuntimeError("custom page service dependencies are missing")

    service = MiniAppService(
        sensenova_claw_home=sensenova_claw_home,
        config=config,
        agent_registry=agent_registry,
        gateway=gateway,
    )
    request.app.state.custom_page_service = service
    if not getattr(request.app.state, "custom_page_service_shutdown_registered", False):
        request.app.add_event_handler("shutdown", service.shutdown)
        request.app.state.custom_page_service_shutdown_registered = True
    return service


@router.get("")
async def list_custom_pages(request: Request):
    service = _get_service(request)
    return {"pages": service.load_pages()}


@router.post("")
async def create_custom_page(request: Request, body: CustomPageCreate):
    service = _get_service(request)
    page = await service.create_page(
        {
            "name": body.name,
            "slug": body.slug,
            "description": body.description,
            "icon": body.icon,
            "agent_id": body.agent_id,
            "system_prompt": body.system_prompt,
            "templates": [item.model_dump() for item in body.templates],
            "create_dedicated_agent": body.create_dedicated_agent,
            "workspace_mode": body.workspace_mode,
            "source_project_path": body.source_project_path,
            "builder_type": body.builder_type,
            "generation_prompt": body.generation_prompt,
        }
    )
    return page


@router.get("/{page_id}")
async def get_custom_page(request: Request, page_id: str):
    service = _get_service(request)
    page = service.get_page(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"custom page not found: {page_id}")
    page = dict(page)
    page["runs"] = service.list_runs(page_id)[:5]
    return page


@router.put("/{page_id}")
async def update_custom_page(request: Request, page_id: str, body: CustomPageUpdate):
    service = _get_service(request)
    page = await service.update_page(
        page_id,
        {
            "name": body.name,
            "description": body.description,
            "icon": body.icon,
            "system_prompt": body.system_prompt,
            "templates": [item.model_dump() for item in body.templates] if body.templates is not None else None,
            "workspace_mode": body.workspace_mode,
            "source_project_path": body.source_project_path,
            "builder_type": body.builder_type,
            "generation_prompt": body.generation_prompt,
        },
    )
    if page is None:
        raise HTTPException(status_code=404, detail=f"custom page not found: {page_id}")
    return page


@router.delete("/{page_id}")
async def delete_custom_page(request: Request, page_id: str):
    service = _get_service(request)
    deleted = await service.delete_page(page_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"custom page not found: {page_id}")
    return {"ok": True}


@router.get("/{page_id}/runs")
async def list_custom_page_runs(request: Request, page_id: str):
    service = _get_service(request)
    page = service.get_page(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"custom page not found: {page_id}")
    return {"runs": service.list_runs(page_id)}


@router.post("/{page_id}/generate")
async def trigger_custom_page_generation(
    request: Request,
    page_id: str,
    body: GenerateRequest,
):
    service = _get_service(request)
    page = service.get_page(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"custom page not found: {page_id}")
    run = await service.trigger_generation(
        page_id,
        prompt=body.prompt or str(page.get("generation_prompt") or page.get("description") or page.get("name") or ""),
        requested_by="api.generate",
    )
    refreshed_page = service.get_page(page_id) or page
    return {
        "page": refreshed_page,
        "run": run,
    }


@router.post("/{page_id}/interactions")
async def dispatch_custom_page_interaction(
    request: Request,
    page_id: str,
    body: MiniAppInteractionRequest,
):
    service = _get_service(request)
    page = service.get_page(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"custom page not found: {page_id}")
    result = await service.dispatch_interaction(
        page_id,
        action=body.action,
        payload=body.payload,
        message=body.message,
        session_id=body.session_id,
        refresh_mode=body.refresh_mode,
    )
    return result


@router.post("/{page_id}/actions")
async def dispatch_custom_page_action(
    request: Request,
    page_id: str,
    body: MiniAppActionRequest,
):
    service = _get_service(request)
    page = service.get_page(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"custom page not found: {page_id}")
    result = await service.dispatch_action(
        page_id,
        action=body.action,
        payload=body.payload,
        target=body.target,
        message=body.message,
        session_id=body.session_id,
        refresh_mode=body.refresh_mode,
    )
    return result


@router.api_route("/{page_id}/preview/", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
@router.api_route("/{page_id}/preview/{subpath:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def proxy_custom_page_preview(
    request: Request,
    page_id: str,
    subpath: str = "",
):
    service = _get_service(request)
    page = service.get_page(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"custom page not found: {page_id}")

    try:
        preview = await service.ensure_preview_server(page_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"workspace preview server unavailable: {exc}")

    base_url = str(preview["base_url"]).rstrip("/")
    path = f"/{subpath}" if subpath else "/"
    query = request.url.query
    upstream_url = f"{base_url}{path}"
    if query:
        upstream_url = f"{upstream_url}?{query}"

    body = await request.body()
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {"host", "content-length", "connection"}
    }

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            upstream = await client.request(
                request.method,
                upstream_url,
                content=body,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"workspace preview proxy failed: {exc}")

    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in {"content-length", "connection", "transfer-encoding", "content-encoding"}
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )
