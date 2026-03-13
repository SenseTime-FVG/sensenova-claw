from __future__ import annotations

from enum import Enum
from typing import Any


class ToolRiskLevel(Enum):
    LOW = "low"           # 只读操作，无副作用
    MEDIUM = "medium"     # 有副作用但可控
    HIGH = "high"         # 高风险操作，需用户确认


class Tool:
    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {}
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW

    async def execute(self, **kwargs: Any) -> Any:
        raise NotImplementedError
