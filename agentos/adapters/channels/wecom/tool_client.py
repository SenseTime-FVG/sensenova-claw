"""企业微信协议适配客户端。

第一版只定义最小接口，便于注入 fake client 做单测和 e2e。
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import WecomConfig


@dataclass
class WecomIncomingMessage:
    """企微入站文本消息。"""

    text: str
    chat_id: str
    chat_type: str
    sender_id: str
    message_id: str


class WecomToolClient:
    """企业微信客户端最小实现。

    当前版本仅保留接口边界，真实网络协议后续再补。
    """

    def __init__(self, config: WecomConfig):
        self._config = config

    async def start(self) -> None:
        """启动客户端。"""

    async def stop(self) -> None:
        """停止客户端。"""

    async def send_text(self, target: str, text: str) -> dict:
        """发送文本消息。真实协议在后续版本补充。"""
        return {"success": True, "message_id": f"stub:{target}"}
