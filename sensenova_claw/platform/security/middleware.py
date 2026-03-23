"""认证中间件（Jupyter-lab 风格 token）

从 cookie 或 query param 中提取 token 并验证。
"""

from __future__ import annotations

import logging

from fastapi import Request, WebSocket

from sensenova_claw.platform.security.auth import COOKIE_NAME, TokenAuthService

logger = logging.getLogger(__name__)


def verify_request(request: Request, auth_service: TokenAuthService) -> bool:
    """从 HTTP 请求中提取并验证 token（cookie 优先）"""
    # 1. cookie
    token = request.cookies.get(COOKIE_NAME)
    if token and auth_service.verify(token):
        return True
    # 2. query param
    token = request.query_params.get("token")
    if token and auth_service.verify(token):
        return True
    # 3. Authorization header（向后兼容 CLI 等场景）
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if auth_service.verify(token):
            return True
    return False


def verify_websocket(websocket: WebSocket, auth_service: TokenAuthService) -> bool:
    """从 WebSocket 请求中提取并验证 token（cookie 优先）"""
    # 1. cookie（浏览器同域自动携带）
    token = websocket.cookies.get(COOKIE_NAME)
    if token and auth_service.verify(token):
        return True
    # 2. query param（降级方案）
    token = websocket.query_params.get("token")
    if token and auth_service.verify(token):
        return True
    return False
