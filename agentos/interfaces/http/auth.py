"""认证相关 HTTP API 端点

提供用户登录、注册、Token 刷新等接口。
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from agentos.platform.security.auth import AuthService, User, create_default_user
from agentos.platform.security.middleware import AuthMiddleware
from agentos.adapters.storage.user_repository import UserRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["authentication"])


# ========== Request/Response Models ==========


class RegisterRequest(BaseModel):
    """用户注册请求"""

    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    email: Optional[EmailStr] = None


class LoginRequest(BaseModel):
    """用户登录请求"""

    username: str
    password: str


class TokenResponse(BaseModel):
    """Token 响应"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    """刷新 Token 请求"""

    refresh_token: str


class UserResponse(BaseModel):
    """用户信息响应"""

    user_id: str
    username: str
    email: Optional[str]
    is_active: bool
    is_admin: bool
    created_at: float
    last_login: Optional[float]


class ApiKeyResponse(BaseModel):
    """API Key 响应"""

    api_key: str
    key_id: str
    name: str
    created_at: float


# ========== API 端点 ==========


def create_auth_router(
    auth_service: AuthService,
    user_repo: UserRepository,
    auth_middleware: AuthMiddleware,
    enable_registration: bool = True,
) -> APIRouter:
    """创建认证路由（工厂函数，便于依赖注入）"""

    @router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
    async def register(req: RegisterRequest):
        """
        用户注册

        注意：生产环境建议禁用公开注册或添加邀请码机制
        """
        if not enable_registration:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Public registration is disabled",
            )

        # 检查用户名是否已存在
        existing_user = await user_repo.get_user_by_username(req.username)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already registered",
            )

        # 检查邮箱是否已存在
        if req.email:
            existing_email = await user_repo.get_user_by_email(req.email)
            if existing_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered",
                )

        # 创建用户
        import time as _time
        user = User(
            user_id=str(uuid.uuid4()),
            username=req.username,
            email=req.email,
            password_hash=auth_service.hash_password(req.password),
            is_active=True,
            is_admin=False,
            created_at=_time.time(),
        )

        await user_repo.create_user(user)
        # 注意：user_repo.create_user 已经记录日志

        return UserResponse(**user.to_dict())

    @router.post("/login", response_model=TokenResponse)
    async def login(req: LoginRequest):
        """
        用户登录

        返回 access_token 和 refresh_token
        """
        # 查找用户
        user = await user_repo.get_user_by_username(req.username)
        if not user:
            logger.warning(f"Login failed: user not found (username={req.username})")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
            )

        # 验证密码
        if not auth_service.verify_password(req.password, user.password_hash):
            logger.warning(f"Login failed: incorrect password (username={req.username})")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
            )

        # 检查账户状态
        if not user.is_active:
            logger.warning(f"Login failed: account disabled (username={req.username})")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is disabled",
            )

        # 更新最后登录时间
        await user_repo.update_user_last_login(user.user_id)

        # 生成 Token 对
        token_pair = auth_service.create_token_pair(user)
        logger.info(f"User logged in successfully: username={user.username}, user_id={user.user_id}")

        return TokenResponse(
            access_token=token_pair.access_token,
            refresh_token=token_pair.refresh_token,
            expires_in=token_pair.expires_in,
        )

    @router.post("/refresh", response_model=TokenResponse)
    async def refresh_token(req: RefreshTokenRequest):
        """
        刷新访问令牌

        使用 refresh_token 获取新的 access_token
        """
        try:
            # 验证 refresh token
            payload = auth_service.verify_token(req.refresh_token, token_type="refresh")
            user_id = payload["sub"]

            # 加载用户
            user = await user_repo.get_user_by_id(user_id)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found",
                )

            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is disabled",
                )

            # 生成新的 Token 对
            token_pair = auth_service.create_token_pair(user)
            return TokenResponse(
                access_token=token_pair.access_token,
                refresh_token=token_pair.refresh_token,
                expires_in=token_pair.expires_in,
            )

        except Exception as e:
            logger.warning(f"Refresh token validation failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )

    @router.get("/me", response_model=UserResponse)
    async def get_current_user_info(
        current_user: User = Depends(auth_middleware.get_current_user),
    ):
        """
        获取当前用户信息

        需要在 Authorization Header 中提供 access_token
        """
        return UserResponse(**current_user.to_dict())

    @router.post("/api-key", response_model=ApiKeyResponse)
    async def create_api_key(
        name: str = "default",
        current_user: User = Depends(auth_middleware.get_current_user),
    ):
        """
        创建 API Key（用于机器对机器认证）

        需要登录后调用
        """
        import hashlib
        import time

        # 生成 API Key
        api_key = auth_service.generate_api_key(current_user.user_id, name)
        key_id = str(uuid.uuid4())
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        # 存储到数据库
        await user_repo.create_api_key(
            key_id=key_id,
            user_id=current_user.user_id,
            key_hash=key_hash,
            name=name,
        )

        logger.info(f"API Key created for user: {current_user.username}")

        return ApiKeyResponse(
            api_key=api_key,
            key_id=key_id,
            name=name,
            created_at=time.time(),
        )

    @router.post("/init-admin", response_model=UserResponse)
    async def initialize_admin():
        """
        初始化默认管理员账户（仅在无用户且配置允许时可用）

        用户名: admin
        密码: admin123

        ⚠️ 生产环境应在 config.yml 中设置 security.allow_init_admin: false
        """
        from agentos.platform.config.config import config as app_config
        if not app_config.get("security.allow_init_admin", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin initialization is disabled in configuration",
            )

        # 检查是否已有用户
        users = await user_repo.list_users(limit=1)
        if users:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin already initialized",
            )

        # 创建默认管理员
        admin = create_default_user()
        await user_repo.create_user(admin)
        logger.warning("⚠️  Default admin user created (username=admin, password=admin123) - CHANGE PASSWORD IN PRODUCTION!")

        return UserResponse(**admin.to_dict())

    return router
