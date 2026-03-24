"""通知数据模型。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal


NotificationLevel = Literal["info", "warning", "error", "success"]
NotificationSource = Literal["cron", "agent", "system", "tool", "heartbeat"]


@dataclass
class Notification:
    """统一通知模型。"""

    title: str
    body: str
    level: NotificationLevel = "info"
    source: NotificationSource = "system"
    session_id: str | None = None
    actions: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] | None = None
    id: str = field(default_factory=lambda: f"notif_{uuid.uuid4().hex[:12]}")
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
