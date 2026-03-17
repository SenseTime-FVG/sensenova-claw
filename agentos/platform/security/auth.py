"""JWT Token 认证鉴权模块

提供基于 JWT 的用户认证和授权功能。
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from passlib.context import CryptContext

logger = logging.getLogger(__name__)

# 密码哈希上下文（使用 argon2 代替 bcrypt，更安全且无 72 字节限制）
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


@dataclass
class User:
    """用户模型"""

    user_id: str
    username: str
    email: Optional[str] = None
    password_hash: Optional[str] = None  # 存储在数据库中
    is_active: bool = True
    is_admin: bool = False
    created_at: float = 0.0
    last_login: Optional[float] = None

    def to_dict(self, include_sensitive: bool = False) -> dict:
        """转换为字典（默认不包含敏感信息）"""
        data = {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "is_active": self.is_active,
            "is_admin": self.is_admin,
            "created_at": self.created_at,
            "last_login": self.last_login,
        }
        if include_sensitive:
            data["password_hash"] = self.password_hash
        return data

    @classmethod
    def from_dict(cls, data: dict) -> User:
        """从字典创建用户对象"""
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            email=data.get("email"),
            password_hash=data.get("password_hash"),
            is_active=data.get("is_active", True),
            is_admin=data.get("is_admin", False),
            created_at=data.get("created_at", time.time()),
            last_login=data.get("last_login"),
        )


@dataclass
class TokenPair:
    """Token 对（访问令牌 + 刷新令牌）"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600  # 访问令牌过期时间（秒）


class AuthService:
    """认证服务"""

    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 60,
        refresh_token_expire_days: int = 30,
    ):
        """
        Args:
            secret_key: JWT 签名密钥（至少 32 字符）
            algorithm: JWT 算法
            access_token_expire_minutes: 访问令牌过期时间（分钟）
            refresh_token_expire_days: 刷新令牌过期时间（天）
        """
        if len(secret_key) < 32:
            raise ValueError("Secret key must be at least 32 characters long")
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expire = timedelta(minutes=access_token_expire_minutes)
        self.refresh_token_expire = timedelta(days=refresh_token_expire_days)
        logger.info(
            f"AuthService initialized (algorithm={algorithm}, "
            f"access_expire={access_token_expire_minutes}m, "
            f"refresh_expire={refresh_token_expire_days}d)"
        )

    def hash_password(self, password: str) -> str:
        """哈希密码（使用 argon2，无长度限制）"""
        return pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """验证密码（使用 argon2，无长度限制）"""
        return pwd_context.verify(plain_password, hashed_password)

    def create_access_token(
        self, user_id: str, username: str, is_admin: bool = False
    ) -> str:
        """创建访问令牌（短期有效）"""
        expire = datetime.now(timezone.utc) + self.access_token_expire
        to_encode = {
            "sub": user_id,  # Subject: 用户 ID
            "username": username,
            "is_admin": is_admin,
            "exp": expire,  # Expiration time
            "iat": datetime.now(timezone.utc),  # Issued at
            "jti": str(uuid.uuid4()),  # JWT ID（唯一标识符）
            "type": "access",
        }
        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(self, user_id: str) -> str:
        """创建刷新令牌（长期有效）"""
        expire = datetime.now(timezone.utc) + self.refresh_token_expire
        to_encode = {
            "sub": user_id,
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "jti": str(uuid.uuid4()),
            "type": "refresh",
        }
        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    def create_token_pair(self, user: User) -> TokenPair:
        """创建 Token 对（访问 + 刷新）"""
        access_token = self.create_access_token(
            user.user_id, user.username, user.is_admin
        )
        refresh_token = self.create_refresh_token(user.user_id)
        logger.debug(f"Token pair created for user: {user.username} (user_id={user.user_id})")
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=int(self.access_token_expire.total_seconds()),
        )

    def verify_token(self, token: str, token_type: str = "access") -> dict:
        """
        验证 Token 并返回 Payload

        Args:
            token: JWT Token
            token_type: 期望的 Token 类型（access 或 refresh）

        Returns:
            Token payload 字典

        Raises:
            jwt.ExpiredSignatureError: Token 已过期
            jwt.InvalidTokenError: Token 无效
            ValueError: Token 类型不匹配
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            # 检查 Token 类型
            if payload.get("type") != token_type:
                logger.warning(f"Token type mismatch: expected {token_type}, got {payload.get('type')}")
                raise ValueError(f"Expected {token_type} token, got {payload.get('type')}")

            logger.debug(f"Token verified: user_id={payload.get('sub')}, type={token_type}")
            return payload

        except jwt.ExpiredSignatureError:
            logger.warning(f"Token expired: type={token_type}")
            raise
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            raise

    def generate_api_key(self, user_id: str, name: str = "") -> str:
        """生成 API Key（用于机器对机器认证）"""
        # 格式: agentos_<user_id_hash>_<random>
        user_hash = hashlib.sha256(user_id.encode()).hexdigest()[:8]
        random_part = secrets.token_urlsafe(32)
        api_key = f"agentos_{user_hash}_{random_part}"
        return api_key

    def verify_api_key(self, api_key: str) -> Optional[str]:
        """
        验证 API Key 并返回 user_id

        注意：实际实现需要从数据库查询 API Key
        这里仅提供接口定义
        """
        # 实际应该查询数据库：
        # SELECT user_id FROM api_keys WHERE key_hash = hash(api_key) AND is_active = 1
        raise NotImplementedError("API Key validation requires database implementation")


def create_default_user() -> User:
    """创建默认管理员用户（仅用于开发/初始化）"""
    return User(
        user_id=str(uuid.uuid4()),
        username="admin",
        email="admin@example.com",
        password_hash=pwd_context.hash("admin123"),  # 默认密码
        is_active=True,
        is_admin=True,
        created_at=time.time(),
    )
