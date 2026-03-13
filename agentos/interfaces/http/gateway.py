"""
Gateway API - 从真实 Gateway 读取 channels 和连接信息
"""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/gateway", tags=["gateway"])


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
            "status": "connected",
            "config": {},
        })
    return channels
