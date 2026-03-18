from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid

from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import USER_INPUT, USER_TURN_CANCEL_REQUESTED, TOOL_CONFIRMATION_RESPONSE
from agentos.adapters.channels.base import Channel, OutboundCapable
from agentos.kernel.runtime.publisher import EventPublisher

logger = logging.getLogger(__name__)


class Gateway:
    """Gateway 负责管理多个 Channel、提供统一业务 API、在 Channel 之间路由事件"""

    def __init__(
        self,
        publisher: EventPublisher,
        repo=None,
        agent_registry=None,
    ):
        self.publisher = publisher
        self.repo = repo
        self.agent_registry = agent_registry
        self._channels: dict[str, Channel] = {}
        self._session_bindings: dict[str, str] = {}  # session_id -> channel_id
        self._task: asyncio.Task | None = None

    # ── Channel 管理 ──────────────────────────────────

    def register_channel(self, channel: Channel) -> None:
        """注册一个 Channel 并注入 gateway 引用"""
        channel_id = channel.get_channel_id()
        self._channels[channel_id] = channel
        channel.gateway = self
        logger.info(f"Registered channel: {channel_id}")

    def bind_session(self, session_id: str, channel_id: str) -> None:
        """绑定 session 到 Channel"""
        self._session_bindings[session_id] = channel_id

    def unbind_session(self, session_id: str) -> None:
        """解绑 session"""
        self._session_bindings.pop(session_id, None)

    # ── 会话管理 ──────────────────────────────────────

    async def create_session(
        self, agent_id: str = "default", meta: dict | None = None, channel_id: str = "",
    ) -> dict:
        """创建会话，返回 {session_id, created_at}"""
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        session_meta = dict(meta or {})
        session_meta["agent_id"] = agent_id
        await self.repo.create_session(session_id=session_id, meta=session_meta)
        if channel_id:
            self.bind_session(session_id, channel_id)
        logger.info("Session created: %s (agent=%s, channel=%s)", session_id, agent_id, channel_id)
        return {"session_id": session_id, "created_at": time.time()}

    async def load_session(self, session_id: str, channel_id: str = "") -> dict:
        """加载会话历史事件"""
        if channel_id:
            self.bind_session(session_id, channel_id)
        events = await self.repo.get_session_events(session_id)
        return {"session_id": session_id, "events": events}

    async def delete_session(self, session_id: str) -> None:
        """删除会话及相关数据"""
        await self.repo.delete_session_cascade(session_id)
        self.unbind_session(session_id)
        logger.info("Session deleted: %s", session_id)

    async def rename_session(self, session_id: str, title: str) -> None:
        """重命名会话"""
        await self.repo.update_session_title(session_id, title)
        logger.info("Session renamed: %s -> %s", session_id, title)

    async def list_sessions(self, limit: int = 50) -> list[dict]:
        """列出会话"""
        return await self.repo.list_sessions(limit=limit)

    # ── 消息收发 ──────────────────────────────────────

    async def send_user_input(
        self, session_id: str, content: str,
        attachments: list | None = None, context_files: list | None = None,
        source: str = "websocket",
    ) -> str:
        """发送用户输入，返回 turn_id"""
        turn_id = f"turn_{uuid.uuid4().hex[:12]}"
        await self.publish_from_channel(
            EventEnvelope(
                type=USER_INPUT,
                session_id=session_id,
                turn_id=turn_id,
                source=source,
                payload={
                    "content": content,
                    "attachments": attachments or [],
                    "context_files": context_files or [],
                },
            )
        )
        return turn_id

    async def cancel_turn(
        self, session_id: str, reason: str = "user_cancel", source: str = "websocket",
    ) -> None:
        """取消当前轮次"""
        await self.publish_from_channel(
            EventEnvelope(
                type=USER_TURN_CANCEL_REQUESTED,
                session_id=session_id,
                source=source,
                payload={"reason": reason},
            )
        )

    async def confirm_tool(
        self, session_id: str, tool_call_id: str, approved: bool, source: str = "websocket",
    ) -> None:
        """工具确认响应"""
        await self.publish_from_channel(
            EventEnvelope(
                type=TOOL_CONFIRMATION_RESPONSE,
                session_id=session_id,
                source=source,
                payload={"tool_call_id": tool_call_id, "approved": approved},
            )
        )

    # ── 查询 ──────────────────────────────────────────

    async def list_agents(self) -> list[dict]:
        """列出可用 Agent"""
        if not self.agent_registry:
            return []
        return [
            {"id": a.id, "name": a.name, "description": a.description, "model": a.model}
            for a in self.agent_registry.list_all()
        ]

    async def get_messages(self, session_id: str) -> list[dict]:
        """获取会话消息历史"""
        return await self.repo.get_session_messages(session_id)

    async def get_session_events(self, session_id: str) -> list[dict]:
        """获取会话事件"""
        return await self.repo.get_session_events(session_id)

    async def get_session_turns(self, session_id: str) -> list[dict]:
        """获取会话轮次"""
        return await self.repo.get_session_turns(session_id)

    # ── 事件路由（内部） ─────────────────────────────

    async def publish_from_channel(self, event: EventEnvelope) -> None:
        """从 Channel 接收事件并发布到 PublicEventBus"""
        await self.publisher.publish(event)

    async def start(self) -> None:
        """启动 Gateway 和所有 Channel"""
        for channel in self._channels.values():
            await channel.start()
        self._task = asyncio.create_task(self._loop())
        logger.info("Gateway started")

    async def stop(self) -> None:
        """停止 Gateway 和所有 Channel"""
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        for channel in self._channels.values():
            await channel.stop()
        logger.info("Gateway stopped")

    async def _loop(self) -> None:
        """订阅 PublicEventBus 并分发事件到对应的 Channel"""
        async for event in self.publisher.bus.subscribe():
            await self._dispatch_event(event)

    async def _dispatch_event(self, event: EventEnvelope) -> None:
        """将事件分发到对应的 Channel（支持事件过滤）"""
        if not event.session_id:
            return

        channel_id = self._session_bindings.get(event.session_id)
        if not channel_id:
            return

        channel = self._channels.get(channel_id)
        if not channel:
            return

        event_types = channel.event_filter()
        if event_types is not None and event.type not in event_types:
            return

        try:
            await channel.send_event(event)
        except Exception as exc:
            logger.error(f"Failed to send event to channel {channel_id}: {exc}")

    # ── 主动消息 ──────────────────────────────────────

    async def deliver_to_channel(self, event: EventEnvelope, channel_id: str) -> bool:
        """直接投递事件到指定 Channel（不经过 session 绑定）"""
        channel = self._channels.get(channel_id)
        if not channel:
            logger.warning("deliver_to_channel: channel %s not found", channel_id)
            return False
        try:
            await channel.send_event(event)
            return True
        except Exception as exc:
            logger.error("Delivery to %s failed: %s", channel_id, exc)
            return False

    async def send_outbound(
        self, channel_id: str, target: str, text: str, **kwargs,
    ) -> dict:
        """主动投递消息到指定目标（由 MessageTool 调用）"""
        channel = self._channels.get(channel_id)
        if not channel:
            return {"success": False, "error": f"Channel '{channel_id}' not found"}
        if not isinstance(channel, OutboundCapable):
            return {"success": False, "error": f"Channel '{channel_id}' does not support outbound"}
        return await channel.send_outbound(target=target, text=text, **kwargs)
