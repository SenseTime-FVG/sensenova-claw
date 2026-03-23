"""通知服务单元测试。"""

from __future__ import annotations

import asyncio
import base64
from copy import deepcopy
from types import SimpleNamespace

import pytest

from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.events.types import NOTIFICATION_PUSH, NOTIFICATION_SESSION
from sensenova_claw.kernel.notification.models import Notification
from sensenova_claw.kernel.notification.providers.native import NativeNotificationProvider
from sensenova_claw.kernel.notification.service import NotificationService
from sensenova_claw.platform.config.config import config


async def _wait_for_event(bus: PublicEventBus):
    async for event in bus.subscribe():
        return event


@pytest.fixture(autouse=True)
def restore_notification_config():
    original = deepcopy(config.data)
    yield
    config.data = original


@pytest.mark.asyncio
async def test_browser_notification_publishes_push_event():
    bus = PublicEventBus()
    service = NotificationService(bus=bus)
    config.set("notification.enabled", True)
    config.set("notification.channels", ["browser"])
    config.set("notification.browser.enabled", True)

    waiter = asyncio.create_task(_wait_for_event(bus))
    await asyncio.sleep(0.01)

    result = await service.send(Notification(title="Cron", body="Done"), channels=["browser"])
    event = await asyncio.wait_for(waiter, timeout=1)

    assert result == {"browser": True}
    assert event.type == NOTIFICATION_PUSH
    assert event.payload["title"] == "Cron"
    assert event.payload["body"] == "Done"


@pytest.mark.asyncio
async def test_session_notification_requires_session_id():
    bus = PublicEventBus()
    service = NotificationService(bus=bus)
    config.set("notification.enabled", True)
    config.set("notification.channels", ["session"])
    config.set("notification.session.enabled", True)

    result = await service.send(Notification(title="Session", body="No target"), channels=["session"])
    assert result == {"session": False}


@pytest.mark.asyncio
async def test_session_notification_publishes_session_event():
    bus = PublicEventBus()
    service = NotificationService(bus=bus)
    config.set("notification.enabled", True)
    config.set("notification.channels", ["session"])
    config.set("notification.session.enabled", True)

    waiter = asyncio.create_task(_wait_for_event(bus))
    await asyncio.sleep(0.01)

    result = await service.send(
        Notification(title="Attention", body="Review required", session_id="sess_123"),
        channels=["session"],
    )
    event = await asyncio.wait_for(waiter, timeout=1)

    assert result == {"session": True}
    assert event.type == NOTIFICATION_SESSION
    assert event.session_id == "sess_123"
    assert event.payload["body"] == "Review required"


def test_resolve_channels_respects_enabled_flags():
    bus = PublicEventBus()
    service = NotificationService(bus=bus)
    config.set("notification.enabled", True)
    config.set("notification.channels", ["browser", "session", "native"])
    config.set("notification.browser.enabled", True)
    config.set("notification.session.enabled", False)
    config.set("notification.native.enabled", False)

    assert service.resolve_channels() == ["browser"]


def test_explicit_channels_bypass_per_channel_default_flags():
    bus = PublicEventBus()
    service = NotificationService(bus=bus)
    config.set("notification.enabled", True)
    config.set("notification.native.enabled", False)
    config.set("notification.browser.enabled", False)

    assert service.resolve_channels(["native", "browser"]) == ["native", "browser"]


@pytest.mark.parametrize(
    ("platform_name", "which_map", "expected_prefix"),
    [
        ("linux", {"notify-send": "/usr/bin/notify-send"}, ["/usr/bin/notify-send", "Cron", "Done"]),
        ("darwin", {"osascript": "/usr/bin/osascript"}, ["/usr/bin/osascript", "-e"]),
        (
            "win32",
            {"powershell": "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"},
            ["C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand"],
        ),
    ],
)
def test_native_notification_provider_selects_platform_command(
    monkeypatch,
    platform_name,
    which_map,
    expected_prefix,
):
    calls: list[list[str]] = []

    def fake_which(name: str):
        return which_map.get(name)

    def fake_run(args, **kwargs):
        calls.append(list(args))
        return SimpleNamespace(returncode=0)

    from sensenova_claw.kernel.notification.providers import native as native_module

    monkeypatch.setattr(native_module.sys, "platform", platform_name)
    monkeypatch.setattr(native_module.shutil, "which", fake_which)
    monkeypatch.setattr(native_module.subprocess, "run", fake_run)

    provider = NativeNotificationProvider()
    ok = provider._send_sync(Notification(title="Cron", body="Done"))

    assert ok is True
    assert calls
    assert calls[0][: len(expected_prefix)] == expected_prefix


def test_native_notification_provider_windows_script_registers_shortcut(monkeypatch):
    calls: list[list[str]] = []

    def fake_which(name: str):
        mapping = {
            "powershell": "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
        }
        return mapping.get(name)

    def fake_run(args, **kwargs):
        calls.append(list(args))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    from sensenova_claw.kernel.notification.providers import native as native_module

    monkeypatch.setattr(native_module.sys, "platform", "win32")
    monkeypatch.setattr(native_module.shutil, "which", fake_which)
    monkeypatch.setattr(native_module.subprocess, "run", fake_run)

    provider = NativeNotificationProvider()
    ok = provider._send_sync(
        Notification(title="Cron & $done", body="body with <xml> and 'quote'"),
    )

    assert ok is True
    assert calls

    encoded_script = calls[0][-1]
    script = base64.b64decode(encoded_script).decode("utf-16le")

    assert native_module._WINDOWS_TOAST_APP_ID in script
    assert native_module._WINDOWS_TOAST_SHORTCUT_NAME in script
    assert "Sensenova-ClawShortcutInstaller" in script
    assert "CreateToastNotifier($appId).Show($toast)" in script
    assert "<text>Cron &amp; $done</text>" in script
    assert "<text>body with &lt;xml&gt; and 'quote'</text>" in script


def test_native_notification_provider_returns_false_when_command_fails(monkeypatch):
    def fake_which(name: str):
        return {"powershell": "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"}.get(name)

    def fake_run(args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="boom")

    from sensenova_claw.kernel.notification.providers import native as native_module

    monkeypatch.setattr(native_module.sys, "platform", "win32")
    monkeypatch.setattr(native_module.shutil, "which", fake_which)
    monkeypatch.setattr(native_module.subprocess, "run", fake_run)

    provider = NativeNotificationProvider()
    ok = provider._send_sync(Notification(title="Cron", body="Done"))

    assert ok is False
