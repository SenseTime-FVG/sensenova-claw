"""S03: Skills API 全部端点"""
import pytest

pytestmark = pytest.mark.asyncio


class TestSkillsAPI:
    async def test_list(self, test_app):
        r = await test_app.get("/api/skills")
        assert r.status_code == 200
        for s in r.json():
            assert s["category"] in ("builtin", "workspace", "installed")

    async def test_toggle(self, test_app):
        skills = (await test_app.get("/api/skills")).json()
        if skills:
            r = await test_app.patch(
                f"/api/skills/{skills[0]['name']}",
                json={"enabled": False},
            )
            assert r.status_code == 200

    async def test_unified_search(self, test_app):
        r = await test_app.get("/api/skills/search", params={"q": "pdf"})
        assert r.status_code == 200
        data = r.json()
        assert "local_results" in data
        assert "total_local" in data
