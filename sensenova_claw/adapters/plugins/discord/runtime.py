"""Discord runtime：负责对接 Discord SDK。"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import logging
from typing import Any, Awaitable, Callable, Sequence

from .config import DiscordConfig
from .models import DiscordFeatureHooks, DiscordInboundMessage

logger = logging.getLogger(__name__)

DiscordMessageHandler = Callable[[DiscordInboundMessage], Awaitable[None]]


def build_discord_intents(discord_module: Any) -> Any:
    """构造 Discord intents，仅申请当前消息 channel 必需的权限。"""
    intents = discord_module.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.messages = True
    intents.members = False
    return intents


def format_discord_runtime_error(exc: Exception) -> str:
    """格式化 Discord runtime 错误，便于 Gateway 页面展示。"""
    if type(exc).__name__ == "PrivilegedIntentsRequired":
        return (
            "未启用 Discord Privileged Intents：请在 Discord Developer Portal "
            "开启 Message Content Intent，或关闭相关特性后重试"
        )
    return str(exc).strip() or type(exc).__name__


class DiscordRuntime:
    """Discord Bot runtime 的最小实现。"""

    def __init__(
        self,
        config: DiscordConfig,
        *,
        feature_hooks: Sequence[DiscordFeatureHooks] | None = None,
    ):
        self._config = config
        self._feature_hooks = list(feature_hooks or [])
        self._message_handler: DiscordMessageHandler | None = None
        self._client: Any | None = None
        self._connect_task: asyncio.Task | None = None
        self._sensenova_claw_status: dict[str, str] = {"status": "idle"}

    def set_message_handler(self, handler: DiscordMessageHandler) -> None:
        self._message_handler = handler

    async def start(self) -> None:
        if not self._config.bot_token:
            self._sensenova_claw_status = {"status": "failed", "error": "missing bot token"}
            raise RuntimeError("Discord bot token is required")

        try:
            discord = importlib.import_module("discord")
        except ImportError as exc:
            self._sensenova_claw_status = {"status": "failed", "error": "discord.py not installed"}
            raise ImportError("discord.py is required for DiscordRuntime") from exc

        intents = build_discord_intents(discord)

        runtime = self

        class _SensenovaClawDiscordClient(discord.Client):
            async def on_ready(self) -> None:  # type: ignore[override]
                runtime._sensenova_claw_status = {"status": "ready"}
                logger.info("Discord runtime ready: user=%s", getattr(self.user, "id", "unknown"))
                for hook in runtime._feature_hooks:
                    await hook.on_ready(runtime)

            async def on_message(self, message) -> None:  # type: ignore[override]
                normalized = runtime._normalize_message(message, discord)
                if normalized is None:
                    return
                for hook in runtime._feature_hooks:
                    await hook.on_message(normalized)
                if runtime._message_handler is not None:
                    await runtime._message_handler(normalized)

        self._client = _SensenovaClawDiscordClient(intents=intents)
        self._sensenova_claw_status = {"status": "connecting"}
        try:
            await self._client.login(self._config.bot_token)
            self._connect_task = asyncio.create_task(self._client.connect(reconnect=True))
        except Exception as exc:
            self._sensenova_claw_status = {"status": "failed", "error": format_discord_runtime_error(exc)}
            raise

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.close()
        if self._connect_task is not None and not self._connect_task.done():
            self._connect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._connect_task
        self._connect_task = None
        self._sensenova_claw_status = {"status": "stopped"}

    async def send_text(
        self,
        channel_id: str,
        text: str,
        *,
        message_reference: str | None = None,
    ) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("Discord runtime is not started")

        channel = self._client.get_channel(int(channel_id))
        if channel is None:
            channel = await self._client.fetch_channel(int(channel_id))

        kwargs: dict[str, Any] = {}
        if message_reference:
            kwargs["reference"] = channel.get_partial_message(int(message_reference))
        sent = await channel.send(text, **kwargs)
        return {"success": True, "message_id": str(sent.id)}

    def _normalize_message(self, message: Any, discord: Any) -> DiscordInboundMessage | None:
        if message.author is None or getattr(message.author, "bot", False):
            return None

        text = (getattr(message, "content", "") or "").strip()
        if not text:
            return None

        channel = message.channel
        channel_type = "group"
        thread_id: str | None = None
        parent_channel_id: str | None = None
        guild_id = str(message.guild.id) if message.guild else None

        if isinstance(channel, discord.Thread):
            channel_type = "thread"
            thread_id = str(channel.id)
            parent = getattr(channel, "parent", None)
            parent_channel_id = str(parent.id) if parent is not None else None
        elif isinstance(channel, discord.DMChannel):
            channel_type = "dm"

        mentioned_bot = False
        if self._client is not None and getattr(self._client, "user", None) is not None:
            bot_user = self._client.user
            mentioned_bot = any(getattr(member, "id", None) == getattr(bot_user, "id", None) for member in message.mentions)

        return DiscordInboundMessage(
            text=text,
            channel_id=str(channel.id),
            channel_type=channel_type,
            sender_id=str(message.author.id),
            sender_name=getattr(message.author, "display_name", None) or getattr(message.author, "name", ""),
            message_id=str(message.id),
            guild_id=guild_id,
            thread_id=thread_id,
            parent_channel_id=parent_channel_id,
            mentioned_bot=mentioned_bot,
        )
