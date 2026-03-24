"""Token 认证模块

首次启动生成随机 token 并持久化到文件，后续重启自动复用已有 token。
通过 URL 或手动输入验证身份，cookie 持久化。
Token 存储在 ~/.sensenova-claw/token 供 CLI 等本地工具自动读取。
"""

from __future__ import annotations

import logging
import os
import secrets
import stat
from pathlib import Path

logger = logging.getLogger(__name__)

# Cookie 名称
COOKIE_NAME = "sensenova_claw_token"
# Cookie 有效期（秒），30 天
COOKIE_MAX_AGE = 30 * 24 * 3600
# Token 文件路径
TOKEN_FILENAME = "token"


class TokenAuthService:
    """基于持久化 token 的认证服务（首次生成，后续复用）"""

    def __init__(self, sensenova_claw_home: str | Path | None = None) -> None:
        self._token_file: Path | None = None

        # 优先从已有 token 文件读取，保证重启后 token 不变
        existing_token = read_token_file(sensenova_claw_home) if sensenova_claw_home else None
        if existing_token:
            self.token = existing_token
            self._token_file = Path(sensenova_claw_home) / TOKEN_FILENAME
            logger.info("TokenAuthService initialized (token loaded from file)")
        else:
            self.token = secrets.token_urlsafe(32)
            # 写入 token 文件供 CLI 读取及下次启动复用
            if sensenova_claw_home:
                self._write_token_file(Path(sensenova_claw_home))
            logger.info("TokenAuthService initialized (new token generated)")

    def verify(self, token: str) -> bool:
        """验证 token 是否匹配"""
        return secrets.compare_digest(token, self.token)

    def _write_token_file(self, home: Path) -> None:
        """将 token 写入 {sensenova_claw_home}/token，权限 600"""
        try:
            token_file = home / TOKEN_FILENAME
            token_file.parent.mkdir(parents=True, exist_ok=True)
            token_file.write_text(self.token, encoding="utf-8")
            # 仅限所有者可读写（Unix）
            try:
                os.chmod(token_file, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass  # Windows 不支持 Unix 权限
            self._token_file = token_file
            logger.info("Token written to %s", token_file)
        except Exception:
            logger.warning("Failed to write token file", exc_info=True)


def read_token_file(sensenova_claw_home: str | Path | None = None) -> str | None:
    """从 {sensenova_claw_home}/token 读取 token（供 CLI 等客户端使用）"""
    if not sensenova_claw_home:
        sensenova_claw_home = Path.home() / ".sensenova-claw"
    token_file = Path(sensenova_claw_home) / TOKEN_FILENAME
    if token_file.exists():
        try:
            return token_file.read_text(encoding="utf-8").strip()
        except Exception:
            return None
    return None
