"""通知分发服务。"""

from __future__ import annotations

import logging
from typing import Iterable

from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.notification.models import Notification
from agentos.kernel.notification.providers import (
    BrowserNotificationProvider,
    ElectronNotificationProvider,
    NativeNotificationProvider,
    NotificationProvider,
    SessionNotificationProvider,
)
from agentos.platform.config.config import config

logger = logging.getLogger(__name__)

_DEFAULT_CHANNELS = ["browser", "session"]


class NotificationService:
    """按配置分发通知到不同 provider。"""

    def __init__(self, bus: PublicEventBus, providers: dict[str, NotificationProvider] | None = None):
        self._bus = bus
        self._providers = providers or {
            "browser": BrowserNotificationProvider(bus),
            "session": SessionNotificationProvider(bus),
            "native": NativeNotificationProvider(),
            "electron": ElectronNotificationProvider(),
        }

    def register(self, provider: NotificationProvider) -> None:
        """注册或覆盖通知 provider。"""
        self._providers[provider.channel_name] = provider

    def get_config(self) -> dict:
        """返回当前通知配置。"""
        return {
            "enabled": bool(config.get("notification.enabled", True)),
            "channels": list(config.get("notification.channels", _DEFAULT_CHANNELS)),
            "native": {"enabled": bool(config.get("notification.native.enabled", False))},
            "browser": {"enabled": bool(config.get("notification.browser.enabled", True))},
            "electron": {"enabled": bool(config.get("notification.electron.enabled", False))},
            "session": {"enabled": bool(config.get("notification.session.enabled", True))},
        }

    def resolve_channels(self, channels: Iterable[str] | None = None) -> list[str]:
        """解析最终启用的通知渠道。"""
        cfg = self.get_config()
        if not cfg["enabled"]:
            return []

        explicit_request = channels is not None
        requested = list(channels) if explicit_request else list(cfg["channels"])
        resolved: list[str] = []
        for name in requested:
            if not isinstance(name, str):
                continue
            if not explicit_request and not cfg.get(name, {}).get("enabled", False):
                continue
            if name in self._providers:
                resolved.append(name)
        return resolved

    async def send(self, notification: Notification, channels: Iterable[str] | None = None) -> dict[str, bool]:
        """发送通知到指定或默认渠道。"""
        results: dict[str, bool] = {}
        for channel_name in self.resolve_channels(channels):
            provider = self._providers.get(channel_name)
            if not provider:
                logger.warning("未知通知 provider: %s", channel_name)
                continue
            try:
                results[channel_name] = await provider.send(notification)
            except Exception:
                logger.exception("通知发送失败 provider=%s title=%s", channel_name, notification.title)
                results[channel_name] = False
        return results
