"""
Gateway API - 从真实 Gateway 读取 channels 和连接信息
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from agentos.adapters.plugins.whatsapp.status_api import build_whatsapp_status

router = APIRouter(prefix="/api/gateway", tags=["gateway"])


def _read_channel_runtime_status(channel: object) -> str:
    """从 channel 自身或其内部 runtime/client 上提取统一状态。"""
    status_sources = (
        getattr(channel, "_agentos_status", None),
        getattr(getattr(channel, "_runtime", None), "_agentos_status", None),
        getattr(getattr(channel, "_client", None), "_agentos_status", None),
    )
    for source in status_sources:
        if isinstance(source, dict):
            status = str(source.get("status", "")).strip()
            if status:
                return status
    return "connected"


@router.get("/stats")
async def get_gateway_stats(request: Request):
    """获取 Gateway 统计信息"""
    services = request.app.state.services
    gw = services.gateway

    total_channels = len(gw._channels)
    active_sessions = len(gw._session_bindings)

    sessions = await services.repo.list_sessions(limit=9999)

    return {
        "totalChannels": total_channels,
        "activeChannels": total_channels,
        "totalConnections": active_sessions,
        "totalSessions": len(sessions),
    }


@router.get("/channels")
async def list_channels(request: Request):
    """获取所有已注册的 Channels"""
    services = request.app.state.services
    gw = services.gateway

    channels = []
    for channel_id, channel in gw._channels.items():
        channels.append({
            "id": channel_id,
            "name": channel_id,
            "type": channel_id.split("_")[0] if "_" in channel_id else channel_id,
            "status": _read_channel_runtime_status(channel),
            "config": {},
        })
    return channels


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
