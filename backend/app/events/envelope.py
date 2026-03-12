from __future__ import annotations

import time
import uuid
from typing import Any

from pydantic import BaseModel, Field


class EventEnvelope(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str
    ts: float = Field(default_factory=lambda: time.time())
    session_id: str
    agent_id: str = "default"
    turn_id: str | None = None
    step_id: str | None = None
    trace_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str = "system"
