"""用户数据仓储（扩展 Repository）

添加用户管理功能到现有的 Repository 类。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Optional

from agentos.platform.security.auth import User

logger = logging.getLogger(__name__)


# 用户表 Schema
USER_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE,
    password_hash TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    is_admin INTEGER DEFAULT 0,
    created_at REAL NOT NULL,
    last_login REAL,
    metadata TEXT
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE TABLE IF NOT EXISTS api_keys (
    key_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    key_hash TEXT UNIQUE NOT NULL,
    name TEXT,
    is_active INTEGER DEFAULT 1,
    created_at REAL NOT NULL,
    expires_at REAL,
    last_used REAL,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);

-- 扩展 sessions 表，添加 user_id 列（向后兼容）
-- 注意：这需要在现有 Repository 初始化后执行
"""


class UserRepository:
    """用户数据仓储（Mixin for Repository）"""

    def __init__(self, db_path: str):
        """初始化用户仓储"""
        self.db_path = db_path
        self._init_user_tables()
        logger.info(f"UserRepository initialized (db_path={db_path})")

    def _init_user_tables(self) -> None:
        """初始化用户相关表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 创建 users 和 api_keys 表
            cursor.executescript(USER_SCHEMA_SQL)

            # 检查 sessions 表是否有 user_id 列，没有则添加
            cursor.execute("PRAGMA table_info(sessions)")
            columns = [row[1] for row in cursor.fetchall()]
            if "user_id" not in columns:
                cursor.execute("ALTER TABLE sessions ADD COLUMN user_id TEXT")
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)"
                )

            conn.commit()
        finally:
            conn.close()

    async def create_user(self, user: User) -> None:
        """创建用户"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO users (
                    user_id, username, email, password_hash,
                    is_active, is_admin, created_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user.user_id,
                    user.username,
                    user.email,
                    user.password_hash,
                    1 if user.is_active else 0,
                    1 if user.is_admin else 0,
                    user.created_at,
                    json.dumps({}),
                ),
            )
            conn.commit()
            logger.info(f"User created: username={user.username}, user_id={user.user_id}, is_admin={user.is_admin}")
        except sqlite3.IntegrityError as e:
            logger.error(f"Failed to create user {user.username}: {e}")
            raise ValueError(f"User already exists: {e}")
        finally:
            conn.close()

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """根据 ID 获取用户"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_user(row)
        finally:
            conn.close()

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_user(row)
        finally:
            conn.close()

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """根据邮箱获取用户"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_user(row)
        finally:
            conn.close()

    async def update_user_last_login(self, user_id: str) -> None:
        """更新用户最后登录时间"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE users SET last_login = ? WHERE user_id = ?",
                (time.time(), user_id),
            )
            conn.commit()
        finally:
            conn.close()

    async def list_users(self, limit: int = 100) -> list[User]:
        """列出所有用户"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM users ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            rows = cursor.fetchall()
            return [self._row_to_user(row) for row in rows]
        finally:
            conn.close()

    async def update_user_active_status(self, user_id: str, is_active: bool) -> None:
        """更新用户激活状态"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE users SET is_active = ? WHERE user_id = ?",
                (1 if is_active else 0, user_id),
            )
            conn.commit()
            logger.info(f"User active status updated: user_id={user_id}, is_active={is_active}")
        finally:
            conn.close()

    async def create_api_key(
        self,
        key_id: str,
        user_id: str,
        key_hash: str,
        name: str = "",
        expires_at: Optional[float] = None,
    ) -> None:
        """创建 API Key"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO api_keys (
                    key_id, user_id, key_hash, name, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (key_id, user_id, key_hash, name, time.time(), expires_at),
            )
            conn.commit()
            logger.info(f"API Key created: key_id={key_id}, user_id={user_id}, name={name}")
        finally:
            conn.close()

    async def get_user_by_api_key_hash(self, key_hash: str) -> Optional[User]:
        """根据 API Key 哈希获取用户"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT u.* FROM users u
                JOIN api_keys ak ON u.user_id = ak.user_id
                WHERE ak.key_hash = ? AND ak.is_active = 1
                  AND (ak.expires_at IS NULL OR ak.expires_at > ?)
                """,
                (key_hash, time.time()),
            )
            row = cursor.fetchone()
            if not row:
                return None

            # 更新 last_used
            cursor.execute(
                "UPDATE api_keys SET last_used = ? WHERE key_hash = ?",
                (time.time(), key_hash),
            )
            conn.commit()

            return self._row_to_user(row)
        finally:
            conn.close()

    async def revoke_api_key(self, key_id: str) -> None:
        """撤销 API Key"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE api_keys SET is_active = 0 WHERE key_id = ?", (key_id,)
            )
            conn.commit()
            logger.info(f"API Key revoked: key_id={key_id}")
        finally:
            conn.close()

    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> User:
        """将数据库行转换为 User 对象"""
        return User(
            user_id=row["user_id"],
            username=row["username"],
            email=row["email"],
            password_hash=row["password_hash"],
            is_active=bool(row["is_active"]),
            is_admin=bool(row["is_admin"]),
            created_at=row["created_at"],
            last_login=row["last_login"],
        )
