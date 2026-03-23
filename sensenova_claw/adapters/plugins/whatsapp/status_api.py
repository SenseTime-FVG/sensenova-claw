"""WhatsApp 状态序列化辅助。"""

from __future__ import annotations

from typing import Any


def build_whatsapp_status(*, config_data: dict[str, Any], channel: Any | None) -> dict[str, Any]:
    """构建前端使用的 WhatsApp 状态快照。"""
    plugins = config_data.get("plugins", {}) if isinstance(config_data, dict) else {}
    plugin_cfg = plugins.get("whatsapp", {}) if isinstance(plugins, dict) else {}
    enabled = bool(plugin_cfg.get("enabled", False))

    runtime = getattr(channel, "_runtime_state", None)
    channel_config = getattr(channel, "_config", None)
    state = getattr(runtime, "state", "not_initialized")
    phone = getattr(runtime, "phone", None)
    last_error = getattr(runtime, "last_error", None)
    last_qr = getattr(runtime, "last_qr", None)
    last_qr_data_url = getattr(runtime, "last_qr_data_url", None)
    last_status_code = getattr(runtime, "last_status_code", None)
    last_event = getattr(runtime, "last_event", None)
    last_event_at = getattr(runtime, "last_event_at", None)
    debug_message = getattr(runtime, "debug_message", None)

    authorized = enabled and state == "ready"

    return {
        "enabled": enabled,
        "authorized": authorized,
        "state": state,
        "authDir": getattr(channel_config, "auth_dir", None) or plugin_cfg.get("auth_dir"),
        "phone": phone,
        "lastQr": last_qr,
        "lastQrDataUrl": last_qr_data_url,
        "lastError": last_error,
        "lastStatusCode": last_status_code,
        "lastEvent": last_event,
        "lastEventAt": last_event_at,
        "debugMessage": debug_message,
    }
