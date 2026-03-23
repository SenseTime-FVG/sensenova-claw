"""
Gateway API - 从真实 Gateway 读取 channels 和连接信息
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from agentos.adapters.plugins.whatsapp.status_api import build_whatsapp_status

router = APIRouter(prefix="/api/gateway", tags=["gateway"])


def _normalize_error_message(value: object) -> str:
    """统一清洗错误文案，避免把 None 渲染成字符串。"""
    if value is None:
        return ""
    return str(value).strip()


def _normalize_channel_status(value: object) -> str:
    """统一 Channel 状态词，避免前端理解各 runtime 私有命名。"""
    status = str(value).strip()
    if status == "ready":
        return "connected"
    return status


def _read_channel_runtime_state(channel: object) -> tuple[str, str]:
    """从 channel 自身或其内部 runtime/client 上提取统一状态与错误。"""
    status_sources = (
        getattr(channel, "_agentos_status", None),
        getattr(getattr(channel, "_runtime", None), "_agentos_status", None),
        getattr(getattr(channel, "_client", None), "_agentos_status", None),
    )
    for source in status_sources:
        if isinstance(source, dict):
            status = _normalize_channel_status(source.get("status", ""))
            if status:
                error = _normalize_error_message(source.get("error", ""))
                return status, error
    return "connected", ""


def _build_channel_rows(request: Request) -> list[dict]:
    services = request.app.state.services
    gw = services.gateway
    plugin_registry = getattr(request.app.state, "plugin_registry", None)

    channels: list[dict] = []
    seen_ids: set[str] = set()

    for channel_id, channel in gw._channels.items():
        status, error = _read_channel_runtime_state(channel)
        channels.append({
            "id": channel_id,
            "name": channel_id,
            "type": channel_id.split("_")[0] if "_" in channel_id else channel_id,
            "status": status,
            "error": error,
            "config": {},
        })
        seen_ids.add(channel_id)

    if plugin_registry is None:
        return channels

    plugin_states = getattr(plugin_registry, "_plugin_states", {})
    plugin_defs = getattr(plugin_registry, "_plugins", {})
    for plugin_id, definition in plugin_defs.items():
        state = plugin_states.get(plugin_id, {})
        if not state.get("enabled"):
            continue
        if plugin_id in seen_ids or state.get("registered_channel_id") in seen_ids:
            continue
        channels.append({
            "id": plugin_id,
            "name": getattr(definition, "name", plugin_id),
            "type": plugin_id,
            "status": _normalize_channel_status(state.get("status", "disconnected")) or "disconnected",
            "error": _normalize_error_message(state.get("error", "")),
            "config": {},
        })
    return channels


@router.get("/stats")
async def get_gateway_stats(request: Request):
    """获取 Gateway 统计信息"""
    services = request.app.state.services
    gw = services.gateway
    channel_rows = _build_channel_rows(request)

    sessions = await services.repo.list_sessions(limit=9999)

    return {
        "totalChannels": len(channel_rows),
        "activeChannels": sum(1 for row in channel_rows if row["status"] == "connected"),
        "totalConnections": len(gw._session_bindings),
        "totalSessions": len(sessions),
    }


@router.get("/channels")
async def list_channels(request: Request):
    """获取所有已注册的 Channels"""
    return _build_channel_rows(request)


@router.get("/whatsapp/status")
async def get_whatsapp_status(request: Request):
    """获取 WhatsApp 登录与运行状态。"""
    services = request.app.state.services
    gw = services.gateway
    cfg = request.app.state.config

    channel = gw._channels.get("whatsapp")
    return build_whatsapp_status(
        config_data=getattr(cfg, "data", {}),
        channel=channel,
    )
