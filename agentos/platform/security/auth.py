"""Token 认证模块（Jupyter-lab 风格）

服务启动时生成随机 token，通过 URL 或手动输入验证身份，cookie 持久化。
"""

from __future__ import annotations

import logging
import secrets

logger = logging.getLogger(__name__)

# Cookie 名称
COOKIE_NAME = "agentos_token"
# Cookie 有效期（秒），30 天
COOKIE_MAX_AGE = 30 * 24 * 3600


class TokenAuthService:
    """基于启动 token 的认证服务（每次启动重新生成）"""

    def __init__(self) -> None:
        self.token = secrets.token_urlsafe(32)
        logger.info("TokenAuthService initialized (token generated)")

    def verify(self, token: str) -> bool:
        """验证 token 是否匹配"""
        return secrets.compare_digest(token, self.token)
