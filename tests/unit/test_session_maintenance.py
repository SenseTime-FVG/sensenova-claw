"""SessionMaintenance 单元测试 — 使用真实 Repository（SQLite 临时 DB），无 mock"""
from __future__ import annotations

import time

import pytest
import pytest_asyncio

from agentos.adapters.storage.repository import Repository
from agentos.kernel.runtime.session_maintenance import SessionMaintenance
from agentos.platform.config.config import Config


@pytest_asyncio.fixture
async def repo(tmp_path):
    r = Repository(db_path=str(tmp_path / "maint_test.db"))
    await r.init()
    return r


class TestPruneExpired:
    """清理超期会话测试"""

    async def test_prune_removes_old_sessions(self, repo):
        """prune_expired 应删除超期的会话"""
        sm = SessionMaintenance(repo)

        # 创建一个 session 然后手动把 last_active 改到很久之前
        await repo.create_session("old_session")
        import sqlite3
        conn = sqlite3.connect(repo.db_path)
        # 将 last_active 设为 60 天前
        old_time = time.time() - 60 * 86400
        conn.execute("UPDATE sessions SET last_active = ? WHERE session_id = ?", (old_time, "old_session"))
        conn.commit()
        conn.close()

        result = await sm.prune_expired(max_age_days=7)
        assert result == 1

        # 验证 session 已被删除
        sessions = await repo.list_sessions()
        assert len(sessions) == 0

    async def test_prune_keeps_recent_sessions(self, repo):
        """最近活跃的 session 不应被清理"""
        sm = SessionMaintenance(repo)
        await repo.create_session("recent_session")
        result = await sm.prune_expired(max_age_days=7)
        assert result == 0

        sessions = await repo.list_sessions()
        assert len(sessions) == 1

    async def test_prune_default_30_days(self, repo):
        """默认参数为 30 天"""
        sm = SessionMaintenance(repo)
        result = await sm.prune_expired()
        assert result == 0  # 刚创建不会被清理


class TestCapSessions:
    """限制会话总数测试"""

    async def test_cap_removes_excess(self, repo):
        """超出上限时删除最旧的 session"""
        sm = SessionMaintenance(repo)
        # 创建 5 个 session
        for i in range(5):
            await repo.create_session(f"s{i}")

        result = await sm.cap_sessions(max_count=3)
        assert result == 2

        sessions = await repo.list_sessions()
        assert len(sessions) == 3

    async def test_cap_noop_when_under_limit(self, repo):
        """不超限时不删除"""
        sm = SessionMaintenance(repo)
        await repo.create_session("s1")
        result = await sm.cap_sessions(max_count=100)
        assert result == 0

    async def test_cap_default_500(self, repo):
        """默认上限 500"""
        sm = SessionMaintenance(repo)
        await repo.create_session("s1")
        result = await sm.cap_sessions()
        assert result == 0


class TestRunMaintenance:
    """完整维护流程测试"""

    async def test_run_maintenance_executes_both(self, repo):
        """run_maintenance 应同时执行 prune 和 cap"""
        sm = SessionMaintenance(repo)
        # 正常执行不应抛异常
        await sm.run_maintenance()

    async def test_run_maintenance_actually_cleans(self, repo):
        """创建一些超期 session，验证 run_maintenance 实际清理"""
        sm = SessionMaintenance(repo)

        # 创建超期 session
        await repo.create_session("old1")
        await repo.create_session("old2")
        import sqlite3
        conn = sqlite3.connect(repo.db_path)
        old_time = time.time() - 60 * 86400
        conn.execute("UPDATE sessions SET last_active = ? WHERE session_id IN ('old1', 'old2')", (old_time,))
        conn.commit()
        conn.close()

        # 创建最近的 session
        await repo.create_session("recent1")

        await sm.run_maintenance()

        sessions = await repo.list_sessions()
        session_ids = {s["session_id"] for s in sessions}
        assert "old1" not in session_ids
        assert "old2" not in session_ids
        assert "recent1" in session_ids
