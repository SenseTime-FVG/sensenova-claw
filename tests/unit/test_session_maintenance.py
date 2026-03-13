"""SessionMaintenance 单元测试"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agentos.kernel.runtime.session_maintenance import SessionMaintenance


class TestPruneExpired:
    """清理超期会话测试"""

    @pytest.mark.asyncio
    async def test_prune_delegates_to_repo(self):
        repo = AsyncMock()
        repo.prune_sessions.return_value = 5
        sm = SessionMaintenance(repo)
        result = await sm.prune_expired(max_age_days=7)
        assert result == 5
        repo.prune_sessions.assert_called_once_with(7)

    @pytest.mark.asyncio
    async def test_prune_default_30_days(self):
        repo = AsyncMock()
        repo.prune_sessions.return_value = 0
        sm = SessionMaintenance(repo)
        await sm.prune_expired()
        repo.prune_sessions.assert_called_once_with(30)


class TestCapSessions:
    """限制会话总数测试"""

    @pytest.mark.asyncio
    async def test_cap_delegates_to_repo(self):
        repo = AsyncMock()
        repo.cap_sessions.return_value = 3
        sm = SessionMaintenance(repo)
        result = await sm.cap_sessions(max_count=100)
        assert result == 3
        repo.cap_sessions.assert_called_once_with(100)

    @pytest.mark.asyncio
    async def test_cap_default_500(self):
        repo = AsyncMock()
        repo.cap_sessions.return_value = 0
        sm = SessionMaintenance(repo)
        await sm.cap_sessions()
        repo.cap_sessions.assert_called_once_with(500)


class TestRunMaintenance:
    """完整维护流程测试"""

    @pytest.mark.asyncio
    @patch("agentos.kernel.runtime.session_maintenance.config")
    async def test_run_maintenance_reads_config(self, mock_config):
        mock_config.get.side_effect = lambda k, d=None: {
            "session.maintenance.prune_after_days": 14,
            "session.maintenance.max_sessions": 200,
        }.get(k, d)
        repo = AsyncMock()
        repo.prune_sessions.return_value = 2
        repo.cap_sessions.return_value = 1
        sm = SessionMaintenance(repo)
        await sm.run_maintenance()
        repo.prune_sessions.assert_called_once_with(14)
        repo.cap_sessions.assert_called_once_with(200)

    @pytest.mark.asyncio
    @patch("agentos.kernel.runtime.session_maintenance.config")
    async def test_run_maintenance_uses_defaults(self, mock_config):
        mock_config.get.side_effect = lambda k, d=None: d
        repo = AsyncMock()
        repo.prune_sessions.return_value = 0
        repo.cap_sessions.return_value = 0
        sm = SessionMaintenance(repo)
        await sm.run_maintenance()
        repo.prune_sessions.assert_called_once_with(30)
        repo.cap_sessions.assert_called_once_with(500)

    @pytest.mark.asyncio
    @patch("agentos.kernel.runtime.session_maintenance.config")
    async def test_run_maintenance_no_log_when_nothing_done(self, mock_config):
        """pruned=0, capped=0 时不打日志（不报错即可）"""
        mock_config.get.side_effect = lambda k, d=None: d
        repo = AsyncMock()
        repo.prune_sessions.return_value = 0
        repo.cap_sessions.return_value = 0
        sm = SessionMaintenance(repo)
        await sm.run_maintenance()  # 不抛异常
