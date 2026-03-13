"""MessageTool：Agent 主动发送消息到指定渠道和目标"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from agentos.capabilities.tools.base import Tool, ToolRiskLevel

if TYPE_CHECKING:
    from agentos.interfaces.ws.gateway import Gateway
    from agentos.kernel.runtime.publisher import EventPublisher


class MessageTool(Tool):
    name = "message"
    description = (
        "主动发送消息到指定渠道和目标。"
        "channel: 渠道名 (feishu)。"
        "target: 目标 ID (chat_id 或 user:<open_id>)。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "description": "目标渠道 (feishu)",
                "default": "feishu",
            },
            "target": {
                "type": "string",
                "description": "目标 ID。飞书: chat_id 或 user:<open_id>",
            },
            "message": {
                "type": "string",
                "description": "消息内容 (支持 Markdown)",
            },
        },
        "required": ["target", "message"],
    }
    risk_level = ToolRiskLevel.MEDIUM

    def __init__(self, gateway: Gateway, publisher: EventPublisher):
        self._gateway = gateway
        self._publisher = publisher

    async def execute(self, **kwargs: Any) -> Any:
        channel = kwargs.get("channel", "feishu")
        target = kwargs.get("target")
        message = kwargs.get("message", "")

        if not target:
            return {"success": False, "error": "target is required"}

        result = await self._gateway.send_outbound(
            channel_id=channel, target=target, text=message,
        )

        if result.get("success"):
            from agentos.kernel.events.envelope import EventEnvelope
            from agentos.kernel.events.types import MESSAGE_OUTBOUND_SENT
            await self._publisher.publish(EventEnvelope(
                type=MESSAGE_OUTBOUND_SENT,
                session_id=kwargs.get("_session_id", ""),
                source="message_tool",
                payload={
                    "channel": channel,
                    "target": target,
                    "message_preview": message[:200],
                    "message_id": result.get("message_id"),
                },
            ))

        return result
