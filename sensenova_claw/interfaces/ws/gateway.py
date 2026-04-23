from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid

from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.router import BusRouter
from sensenova_claw.kernel.events.types import USER_INPUT, USER_TURN_CANCEL_REQUESTED, TOOL_CONFIRMATION_RESPONSE
from sensenova_claw.adapters.channels.base import Channel, OutboundCapable
from sensenova_claw.kernel.runtime.publisher import EventPublisher

logger = logging.getLogger(__name__)


class Gateway:
    """Gateway 负责管理多个 Channel、提供统一业务 API、在 Channel 之间路由事件"""

    def __init__(
        self,
        publisher: EventPublisher,
        repo=None,
        agent_registry=None,
        bus_router: BusRouter | None = None,
    ):
        self.publisher = publisher
        self.repo = repo
        self.agent_registry = agent_registry
        self.bus_router = bus_router
        self._channels: dict[str, Channel] = {}
        self._session_bindings: dict[str, set[str]] = {}  # session_id -> set of channel_ids
        self._task: asyncio.Task | None = None
        # BusRouter GC 销毁 session 时联动清理 Gateway 绑定和 Channel 内部映射
        if bus_router:
            bus_router.on_destroy(self.on_session_destroyed)

    # ── Channel 管理 ──────────────────────────────────

    def register_channel(self, channel: Channel) -> None:
        """注册一个 Channel 并注入 gateway 引用"""
        channel_id = channel.get_channel_id()
        self._channels[channel_id] = channel
        channel.gateway = self
        logger.info(f"Registered channel: {channel_id}")

    def bind_session(self, session_id: str, channel_id: str) -> None:
        """绑定 session 到 Channel（支持多 Channel 同时绑定）"""
        self._session_bindings.setdefault(session_id, set()).add(channel_id)

    def unbind_session(self, session_id: str, channel_id: str | None = None) -> None:
        """解绑 session。指定 channel_id 时只移除该绑定，否则移除全部。"""
        if channel_id is None:
            self._session_bindings.pop(session_id, None)
        else:
            bindings = self._session_bindings.get(session_id)
            if bindings:
                bindings.discard(channel_id)
                if not bindings:
                    del self._session_bindings[session_id]

    async def on_session_destroyed(self, session_id: str) -> None:
        """BusRouter GC 销毁 session 时的回调：清理绑定并通知相关 Channel。"""
        channel_ids = self._session_bindings.pop(session_id, None)
        if not channel_ids:
            return
        for channel_id in channel_ids:
            channel = self._channels.get(channel_id)
            if channel:
                try:
                    channel.on_session_expired(session_id)
                except Exception:
                    logger.exception("Channel %s on_session_expired failed for %s", channel_id, session_id)
        logger.debug("Gateway cleaned up session %s (channels: %s)", session_id, channel_ids)

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

    async def list_sessions(self, limit: int = 50, include_hidden: bool = False) -> list[dict]:
        """列出会话"""
        return await self.repo.list_sessions(limit=limit, include_hidden=include_hidden)

    async def list_sessions_page(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        include_hidden: bool = False,
        search_term: str = "",
        status: str = "all",
        include_ancestors: bool = False,
        include_all: bool = False,
    ) -> dict:
        """按页列出会话。"""
        return await self.repo.list_sessions_page(
            page=page,
            page_size=page_size,
            include_hidden=include_hidden,
            search_term=search_term,
            status=status,
            include_ancestors=include_ancestors,
            include_all=include_all,
        )

    # ── 消息收发 ──────────────────────────────────────

    async def send_user_input(
        self, session_id: str, content: str,
        attachments: list | None = None, context_files: list | None = None,
        meta: dict | None = None,
        source: str = "websocket",
    ) -> str:
        """发送用户输入，返回 turn_id"""
        turn_id = f"turn_{uuid.uuid4().hex[:12]}"
        payload = {
            "content": content,
            "attachments": attachments or [],
            "context_files": context_files or [],
        }
        if meta:
            payload["meta"] = meta
        await self.publish_from_channel(
            EventEnvelope(
                type=USER_INPUT,
                session_id=session_id,
                turn_id=turn_id,
                source=source,
                payload=payload,
            )
        )
        return turn_id

    async def cancel_turn(
        self, session_id: str, reason: str = "user_cancel", source: str = "websocket",
    ) -> None:
        """取消当前轮次"""
        event = EventEnvelope(
            type=USER_TURN_CANCEL_REQUESTED,
            session_id=session_id,
            source=source,
            payload={"reason": reason},
        )
        private_bus = self.bus_router.get(session_id) if self.bus_router else None
        if private_bus:
            await private_bus.publish(event)
            return
        await self.publish_from_channel(event)

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
            try:
                await channel.start()
            except Exception as exc:
                status = getattr(channel, "_sensenova_claw_status", None)
                if not isinstance(status, dict):
                    channel._sensenova_claw_status = {}
                    status = channel._sensenova_claw_status
                status["status"] = "failed"
                status["error"] = str(exc).strip() or type(exc).__name__
                logger.exception("Failed to start channel: %s", channel.get_channel_id())
        self._task = asyncio.create_task(self._event_loop())
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

    async def _event_loop(self) -> None:
        """订阅 PublicEventBus 并分发事件到对应的 Channel"""
        from sensenova_claw.kernel.events.types import TODOLIST_UPDATED, PROACTIVE_RESULT
        _BROADCAST_EVENTS = {TODOLIST_UPDATED, PROACTIVE_RESULT}

        async for event in self.publisher.bus.subscribe():
            if event.type.startswith("config.") or event.type in _BROADCAST_EVENTS:
                for channel in self._channels.values():
                    try:
                        await channel.send_event(event)
                    except Exception as exc:
                        logger.error("Failed to broadcast event %s to channel: %s", event.type, exc)
            else:
                await self._dispatch_event(event)

    async def _resolve_channel_by_parent_chain(
        self,
        session_id: str,
    ) -> tuple[str | None, str | None, list[str], bool]:
        """按 parent_session_id 向上查找可继承的 channel，并缓存绑定。"""
        if not self.repo or not hasattr(self.repo, "get_session_meta"):
            return None, None, [session_id], False

        visited: set[str] = set()
        chain: list[str] = [session_id]
        current = session_id
        immediate_parent: str | None = None
        inherited_channel: str | None = None
        cache_hit = False

        while current and current not in visited:
            visited.add(current)
            try:
                meta = await self.repo.get_session_meta(current)
            except Exception as exc:  # noqa: BLE001
                logger.warning("resolve parent chain failed session=%s error=%s", current, exc)
                break
            if not isinstance(meta, dict):
                break

            parent_session_id = str(meta.get("parent_session_id", "")).strip()
            if current == session_id:
                immediate_parent = parent_session_id or None
            if not parent_session_id:
                break

            chain.append(parent_session_id)
            parent_bindings = self._session_bindings.get(parent_session_id)
            if parent_bindings:
                inherited_channel = next(iter(parent_bindings))
                for sid in chain[:-1]:
                    existing = self._session_bindings.get(sid)
                    if not existing or inherited_channel not in existing:
                        self.bind_session(sid, inherited_channel)
                        cache_hit = True
                break
            current = parent_session_id

        return inherited_channel, immediate_parent, chain, cache_hit

    async def _dispatch_event(self, event: EventEnvelope) -> None:
        """将事件分发到对应的 Channel（支持事件过滤，支持多 Channel）"""
        if not event.session_id:
            return

        channel_ids = self._session_bindings.get(event.session_id)
        if not channel_ids:
            (
                resolved_channel_id,
                immediate_parent,
                parent_chain,
                cache_hit,
            ) = await self._resolve_channel_by_parent_chain(event.session_id)
            logger.debug(
                "gateway route resolve session=%s parent_session_id=%s chain=%s channel=%s cache_hit=%s",
                event.session_id,
                immediate_parent,
                " -> ".join(parent_chain),
                resolved_channel_id or "none",
                cache_hit,
            )
            if not resolved_channel_id:
                return
            channel_ids = {resolved_channel_id}

        for channel_id in list(channel_ids):
            channel = self._channels.get(channel_id)
            if not channel:
                continue

            event_types = channel.event_filter()
            if event_types is not None and event.type not in event_types:
                continue

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
