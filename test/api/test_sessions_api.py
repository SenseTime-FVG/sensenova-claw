"""Sessions API 端点测试"""
import pytest

pytestmark = pytest.mark.asyncio


class TestSessionsAPI:
    async def test_list_sessions(self, test_app):
        r = await test_app.get("/api/sessions")
        assert r.status_code == 200
        data = r.json()
        assert "sessions" in data

    async def test_health(self, test_app):
        r = await test_app.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"
