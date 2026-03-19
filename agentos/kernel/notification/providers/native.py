"""桌面原生通知 provider。"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import sys
from xml.sax.saxutils import escape

from agentos.kernel.notification.models import Notification
from agentos.kernel.notification.providers.base import NotificationProvider

logger = logging.getLogger(__name__)


def _escape_applescript(value: str) -> str:
    """转义 AppleScript 字符串中的双引号。"""
    return value.replace("\\", "\\\\").replace('"', '\\"')


class NativeNotificationProvider(NotificationProvider):
    """跨平台桌面原生通知。"""

    channel_name = "native"

    async def send(self, notification: Notification) -> bool:
        return await asyncio.to_thread(self._send_sync, notification)

    def _send_sync(self, notification: Notification) -> bool:
        title = notification.title.strip() or "AgentOS"
        body = notification.body.strip() or notification.title.strip() or "Notification"

        try:
            if sys.platform.startswith("linux"):
                notify_send = shutil.which("notify-send")
                if not notify_send:
                    logger.warning("notify-send 不存在，跳过原生通知")
                    return False
                subprocess.run(
                    [notify_send, title, body],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                return True

            if sys.platform == "darwin":
                osascript = shutil.which("osascript")
                if not osascript:
                    logger.warning("osascript 不存在，跳过原生通知")
                    return False
                script = (
                    f'display notification "{_escape_applescript(body)}" '
                    f'with title "{_escape_applescript(title)}"'
                )
                subprocess.run(
                    [osascript, "-e", script],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                return True

            if sys.platform.startswith("win"):
                powershell = shutil.which("powershell") or shutil.which("pwsh")
                if not powershell:
                    logger.warning("PowerShell 不存在，跳过原生通知")
                    return False
                xml = (
                    "<toast><visual><binding template='ToastGeneric'>"
                    f"<text>{escape(title)}</text>"
                    f"<text>{escape(body)}</text>"
                    "</binding></visual></toast>"
                )
                script = (
                    "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
                    "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null;"
                    "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument;"
                    f"$xml.LoadXml(\"{xml}\");"
                    "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml);"
                    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('AgentOS').Show($toast);"
                )
                subprocess.run(
                    [powershell, "-NoProfile", "-Command", script],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                return True
        except Exception:
            logger.exception("原生通知发送失败")
            return False

        logger.warning("当前平台不支持原生通知: %s", sys.platform)
        return False
