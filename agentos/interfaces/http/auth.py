"""认证 HTTP API 端点（Jupyter-lab 风格 token）

提供 token 验证和认证状态查询接口。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from agentos.platform.config.config import config
from agentos.platform.security.auth import COOKIE_MAX_AGE, COOKIE_NAME, TokenAuthService
from agentos.platform.security.middleware import verify_request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["authentication"])


class VerifyTokenRequest(BaseModel):
    """Token 验证请求"""
    token: str


class AuthStatusResponse(BaseModel):
    """认证状态响应"""
    authenticated: bool


def create_auth_router(auth_service: TokenAuthService) -> APIRouter:
    """创建认证路由"""

    @router.post("/verify-token")
    async def verify_token(req: VerifyTokenRequest, response: Response):
        """
        验证 token 并设置 cookie

        前端通过 URL ?token=xxx 或手动输入获得 token 后调用此接口，
        验证成功后在响应中设置 cookie，后续请求自动携带。
        """
        if not auth_service.verify(req.token):
            return {"authenticated": False, "error": "Invalid token"}

        # 设置 cookie
        response.set_cookie(
            key=COOKIE_NAME,
            value=req.token,
            max_age=COOKIE_MAX_AGE,
            httponly=False,  # 前端 JS 需要读取
            samesite="lax",
            path="/",
        )
        logger.info("Token verified, cookie set")
        return {"authenticated": True}

    @router.get("/status")
    async def auth_status(request: Request):
        """
        查询当前认证状态

        auth_enabled 关闭时直接返回 authenticated=true（无需 token）。
        """
        if not config.get("security.auth_enabled", False):
            return AuthStatusResponse(authenticated=True)
        authenticated = verify_request(request, auth_service)
        return AuthStatusResponse(authenticated=authenticated)

    @router.post("/logout")
    async def logout(response: Response):
        """
        登出（清除 cookie）
        """
        response.delete_cookie(key=COOKIE_NAME, path="/")
        return {"ok": True}

    return router
