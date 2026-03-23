"""通知配置与测试 API。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from agentos.kernel.notification.models import Notification

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotificationConfigBody(BaseModel):
    enabled: bool | None = None
    channels: list[str] | None = None
    native: dict[str, Any] | None = None
    browser: dict[str, Any] | None = None
    electron: dict[str, Any] | None = None
    session: dict[str, Any] | None = None


class NotificationTestBody(BaseModel):
    title: str = "AgentOS test notification"
    body: str = "Notification pipeline is working."
    level: str = "info"
    source: str = "system"
    session_id: str | None = None
    channels: list[str] | None = None


@router.get("/config")
async def get_notification_config(request: Request):
    return request.app.state.services.notification_service.get_config()


@router.put("/config")
async def update_notification_config(body: NotificationConfigBody, request: Request):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "No notification config updates provided")

    config_manager = request.app.state.config_manager
    try:
        await config_manager.update("notification", updates)
    except Exception as exc:
        raise HTTPException(500, f"Failed to save notification config: {exc}")

    return request.app.state.services.notification_service.get_config()


@router.post("/test")
async def send_test_notification(body: NotificationTestBody, request: Request):
    notification = Notification(
        title=body.title,
        body=body.body,
        level=body.level,  # type: ignore[arg-type]
        source=body.source,  # type: ignore[arg-type]
        session_id=body.session_id,
        metadata={"test": True},
    )
    results = await request.app.state.services.notification_service.send(notification, channels=body.channels)
    return {"success": any(results.values()) if results else False, "results": results}
