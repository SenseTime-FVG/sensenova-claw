"""QQ runtime 抽象接口。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from .models import QQInboundMessage

QQMessageHandler = Callable[[QQInboundMessage], Awaitable[None]]


class QQRuntime(Protocol):
    """QQ runtime 最小协议。"""

    def set_message_handler(self, handler: QQMessageHandler) -> None: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def send_text(self, target: str, text: str, *, reply_to_message_id: str | None = None) -> dict: ...

