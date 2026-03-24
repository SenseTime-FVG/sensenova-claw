"""Session 生命周期管理

提供会话清理和总量控制功能，在后端启动时执行。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sensenova_claw.platform.config.config import config

if TYPE_CHECKING:
    from sensenova_claw.adapters.storage.repository import Repository

logger = logging.getLogger(__name__)


class SessionMaintenance:
    def __init__(self, repo: Repository):
        self._repo = repo

    async def prune_expired(self, max_age_days: int = 30) -> int:
        """清理超期未活跃的会话及关联数据"""
        return await self._repo.prune_sessions(max_age_days)

    async def cap_sessions(self, max_count: int = 500) -> int:
        """限制会话总数，淘汰最旧的"""
        return await self._repo.cap_sessions(max_count)

    async def run_maintenance(self) -> None:
        """执行完整的维护流程"""
        max_age = int(config.get("session.maintenance.prune_after_days", 30))
        max_count = int(config.get("session.maintenance.max_sessions", 500))
        pruned = await self.prune_expired(max_age)
        capped = await self.cap_sessions(max_count)
        if pruned or capped:
            logger.info("Session maintenance: pruned=%d, capped=%d", pruned, capped)
