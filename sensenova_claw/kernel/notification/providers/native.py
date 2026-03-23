"""桌面原生通知 provider。"""

from __future__ import annotations

import asyncio
import base64
import logging
import shutil
import subprocess
import sys
from xml.sax.saxutils import escape

from sensenova_claw.kernel.notification.models import Notification
from sensenova_claw.kernel.notification.providers.base import NotificationProvider

logger = logging.getLogger(__name__)

_WINDOWS_TOAST_APP_ID = "Sensenova-Claw.DesktopNotification"
_WINDOWS_TOAST_SHORTCUT_NAME = "Sensenova-Claw Notifications.lnk"
_WINDOWS_TOAST_SHORTCUT_DESCRIPTION = "Sensenova-Claw desktop notifications"
_WINDOWS_SHORTCUT_INSTALLER_SOURCE = r"""
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;

[ComImport]
[Guid("00021401-0000-0000-C000-000000000046")]
internal class ShellLink
{
}

[ComImport]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
[Guid("000214F9-0000-0000-C000-000000000046")]
internal interface IShellLinkW
{
    void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszFile, int cchMaxPath, IntPtr pfd, uint fFlags);
    void GetIDList(out IntPtr ppidl);
    void SetIDList(IntPtr pidl);
    void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszName, int cchMaxName);
    void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string pszName);
    void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszDir, int cchMaxPath);
    void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string pszDir);
    void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszArgs, int cchMaxPath);
    void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string pszArgs);
    void GetHotkey(out short pwHotkey);
    void SetHotkey(short wHotkey);
    void GetShowCmd(out int piShowCmd);
    void SetShowCmd(int iShowCmd);
    void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszIconPath, int cchIconPath, out int iIcon);
    void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string pszIconPath, int iIcon);
    void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string pszPathRel, uint dwReserved);
    void Resolve(IntPtr hwnd, uint fFlags);
    void SetPath([MarshalAs(UnmanagedType.LPWStr)] string pszFile);
}

[ComImport]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
[Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")]
internal interface IPropertyStore
{
    int GetCount(out uint cProps);
    int GetAt(uint iProp, out PROPERTYKEY pkey);
    int GetValue(ref PROPERTYKEY key, out PROPVARIANT pv);
    int SetValue(ref PROPERTYKEY key, ref PROPVARIANT pv);
    int Commit();
}

[StructLayout(LayoutKind.Sequential, Pack = 4)]
internal struct PROPERTYKEY
{
    public Guid fmtid;
    public uint pid;
}

[StructLayout(LayoutKind.Sequential)]
internal struct PROPVARIANT : IDisposable
{
    public ushort vt;
    public ushort wReserved1;
    public ushort wReserved2;
    public ushort wReserved3;
    public IntPtr p;
    public int p2;

    public static PROPVARIANT FromString(string value)
    {
        return new PROPVARIANT
        {
            vt = 31,
            p = Marshal.StringToCoTaskMemUni(value),
            p2 = 0,
        };
    }

    public void Dispose()
    {
        NativeMethods.PropVariantClear(ref this);
    }
}

internal static class NativeMethods
{
    [DllImport("ole32.dll")]
    internal static extern int PropVariantClear(ref PROPVARIANT pvar);
}

public static class Sensenova-ClawShortcutInstaller
{
    public static void EnsureShortcut(
        string shortcutPath,
        string targetPath,
        string arguments,
        string description,
        string appId
    )
    {
        var shellLink = (IShellLinkW)new ShellLink();
        shellLink.SetPath(targetPath);
        shellLink.SetArguments(arguments ?? string.Empty);
        shellLink.SetDescription(description ?? string.Empty);
        shellLink.SetWorkingDirectory(System.IO.Path.GetDirectoryName(targetPath) ?? string.Empty);

        var propertyStore = (IPropertyStore)shellLink;
        var appUserModelId = new PROPERTYKEY
        {
            fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"),
            pid = 5,
        };
        var appIdProp = PROPVARIANT.FromString(appId);

        try
        {
            int hr = propertyStore.SetValue(ref appUserModelId, ref appIdProp);
            if (hr != 0)
            {
                Marshal.ThrowExceptionForHR(hr);
            }

            hr = propertyStore.Commit();
            if (hr != 0)
            {
                Marshal.ThrowExceptionForHR(hr);
            }

            ((IPersistFile)shellLink).Save(shortcutPath, true);
        }
        finally
        {
            appIdProp.Dispose();
        }
    }
}
""".strip()


def _escape_applescript(value: str) -> str:
    """转义 AppleScript 字符串中的双引号。"""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _escape_powershell_literal(value: str) -> str:
    """转义 PowerShell 单引号字符串。"""
    return value.replace("'", "''")


def _encode_powershell_script(script: str) -> str:
    """按 PowerShell 约定将脚本编码为 UTF-16LE Base64。"""
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def _build_windows_toast_script(title: str, body: str, powershell_path: str) -> str:
    """构造 Windows Toast 通知脚本，并确保开始菜单快捷方式存在。"""
    xml = (
        "<toast><visual><binding template='ToastGeneric'>"
        f"<text>{escape(title)}</text>"
        f"<text>{escape(body)}</text>"
        "</binding></visual></toast>"
    )
    return "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            "$ProgressPreference = 'SilentlyContinue'",
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null",
            "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null",
            "",
            f"$appId = '{_WINDOWS_TOAST_APP_ID}'",
            f"$shortcutPath = Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs\\{_WINDOWS_TOAST_SHORTCUT_NAME}'",
            f"$shortcutTarget = '{_escape_powershell_literal(powershell_path)}'",
            "$shortcutArguments = '-NoProfile -Command exit'",
            f"$shortcutDescription = '{_escape_powershell_literal(_WINDOWS_TOAST_SHORTCUT_DESCRIPTION)}'",
            "",
            "if (-not ('Sensenova-ClawShortcutInstaller' -as [type])) {",
            "    # 用 C# 直接写入快捷方式的 AppUserModelID，避免 CreateToastNotifier 被系统静默丢弃。",
            "    Add-Type -TypeDefinition @'",
            _WINDOWS_SHORTCUT_INSTALLER_SOURCE,
            "'@",
            "}",
            "",
            "$shortcutDirectory = Split-Path -Parent $shortcutPath",
            "if ($shortcutDirectory -and -not (Test-Path $shortcutDirectory)) {",
            "    New-Item -ItemType Directory -Path $shortcutDirectory -Force | Out-Null",
            "}",
            "",
            "[Sensenova-ClawShortcutInstaller]::EnsureShortcut(",
            "    $shortcutPath,",
            "    $shortcutTarget,",
            "    $shortcutArguments,",
            "    $shortcutDescription,",
            "    $appId",
            ")",
            "",
            "$xmlPayload = @'",
            xml,
            "'@",
            "$toastXml = New-Object Windows.Data.Xml.Dom.XmlDocument",
            "$toastXml.LoadXml($xmlPayload.Trim())",
            "$toast = [Windows.UI.Notifications.ToastNotification]::new($toastXml)",
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)",
            "Start-Sleep -Milliseconds 200",
        ]
    )


def _run_notification_command(command: list[str], *, label: str) -> bool:
    """执行底层通知命令，并记录返回码与输出。"""
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    stdout = (getattr(completed, "stdout", "") or "").strip()
    stderr = (getattr(completed, "stderr", "") or "").strip()
    if completed.returncode != 0:
        logger.warning(
            "%s 执行失败 returncode=%s stdout=%s stderr=%s",
            label,
            completed.returncode,
            stdout,
            stderr,
        )
        return False
    logger.debug("%s 执行完成 stdout=%s stderr=%s", label, stdout, stderr)
    return True


class NativeNotificationProvider(NotificationProvider):
    """跨平台桌面原生通知。"""

    channel_name = "native"

    async def send(self, notification: Notification) -> bool:
        return await asyncio.to_thread(self._send_sync, notification)

    def _send_sync(self, notification: Notification) -> bool:
        title = notification.title.strip() or "Sensenova-Claw"
        body = notification.body.strip() or notification.title.strip() or "Notification"

        try:
            if sys.platform.startswith("linux"):
                notify_send = shutil.which("notify-send")
                if not notify_send:
                    logger.warning("notify-send 不存在，跳过原生通知")
                    return False
                return _run_notification_command(
                    [notify_send, title, body],
                    label="notify-send 原生通知",
                )

            if sys.platform == "darwin":
                osascript = shutil.which("osascript")
                if not osascript:
                    logger.warning("osascript 不存在，跳过原生通知")
                    return False
                script = (
                    f'display notification "{_escape_applescript(body)}" '
                    f'with title "{_escape_applescript(title)}"'
                )
                return _run_notification_command(
                    [osascript, "-e", script],
                    label="osascript 原生通知",
                )

            if sys.platform.startswith("win"):
                powershell = shutil.which("powershell") or shutil.which("pwsh")
                if not powershell:
                    logger.warning("PowerShell 不存在，跳过原生通知")
                    return False
                script = _build_windows_toast_script(
                    title=title,
                    body=body,
                    powershell_path=powershell,
                )
                return _run_notification_command(
                    [
                        powershell,
                        "-NoProfile",
                        "-NonInteractive",
                        "-EncodedCommand",
                        _encode_powershell_script(script),
                    ],
                    label=f"PowerShell 原生通知 exe={powershell}",
                )
        except Exception:
            logger.exception("原生通知发送失败")
            return False

        logger.warning("当前平台不支持原生通知: %s", sys.platform)
        return False
