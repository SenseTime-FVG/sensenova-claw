"""认证中间件和依赖注入

提供 FastAPI 路由保护和 WebSocket 认证。
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, WebSocket, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from agentos.platform.security.auth import AuthService, User
from agentos.adapters.storage.user_repository import UserRepository

logger = logging.getLogger(__name__)

# HTTP Bearer Token 认证方案
security = HTTPBearer()


class AuthMiddleware:
    """认证中间件"""

    def __init__(self, auth_service: AuthService, user_repo: UserRepository):
        self.auth_service = auth_service
        self.user_repo = user_repo

    async def get_current_user(
        self, credentials: HTTPAuthorizationCredentials = Depends(security)
    ) -> User:
        """
        从 HTTP Authorization Header 获取当前用户（依赖注入）

        用法:
            @app.get("/protected")
            async def protected_route(user: User = Depends(auth.get_current_user)):
                return {"message": f"Hello {user.username}"}
        """
        token = credentials.credentials

        try:
            # 验证 access token
            payload = self.auth_service.verify_token(token, token_type="access")
            user_id = payload["sub"]

            # 从数据库加载用户
            user = await self.user_repo.get_user_by_id(user_id)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found",
                )

            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User account is disabled",
                )

            return user

        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {e}",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def get_current_admin_user(self):
        """
        返回一个依赖注入函数，用于获取当前管理员用户（仅管理员可访问）

        用法:
            @app.delete("/users/{user_id}")
            async def delete_user(
                user_id: str,
                admin: User = Depends(auth.get_current_admin_user())
            ):
                ...
        """
        get_user = self.get_current_user

        async def _get_admin(current_user: User = Depends(get_user)) -> User:
            if not current_user.is_admin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Admin privileges required",
                )
            return current_user

        return _get_admin

    async def authenticate_websocket(self, websocket: WebSocket, token: str) -> User:
        """
        WebSocket 连接认证

        Args:
            websocket: WebSocket 连接对象
            token: JWT Token（从查询参数或消息中获取）

        Returns:
            认证通过的用户对象

        Raises:
            WebSocket close: 认证失败时关闭连接
        """
        try:
            # 验证 token
            payload = self.auth_service.verify_token(token, token_type="access")
            user_id = payload["sub"]

            # 加载用户
            user = await self.user_repo.get_user_by_id(user_id)
            if not user:
                await websocket.close(code=4001, reason="User not found")
                raise ValueError("User not found")

            if not user.is_active:
                await websocket.close(code=4003, reason="Account disabled")
                raise ValueError("Account disabled")

            logger.info(f"WebSocket authenticated: user_id={user_id}, username={user.username}")
            return user

        except jwt.ExpiredSignatureError:
            await websocket.close(code=4001, reason="Token expired")
            raise ValueError("Token expired")
        except jwt.InvalidTokenError as e:
            await websocket.close(code=4001, reason=f"Invalid token: {e}")
            raise ValueError(f"Invalid token: {e}")

    async def authenticate_api_key(self, api_key: str) -> User:
        """
        API Key 认证（用于机器对机器通信）

        Args:
            api_key: API Key 字符串

        Returns:
            认证通过的用户对象
        """
        # 计算 API Key 的哈希值
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        # 从数据库查询
        user = await self.user_repo.get_user_by_api_key_hash(key_hash)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is disabled",
            )

        return user
