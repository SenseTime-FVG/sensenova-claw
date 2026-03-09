from __future__ import annotations

from typing import Any


class Tool:
    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {}

    async def execute(self, **kwargs: Any) -> Any:
        raise NotImplementedError
