"""A06: Agent API 全部端点"""
import pytest

pytestmark = pytest.mark.asyncio


class TestAgentsAPI:
    async def test_list(self, test_app):
        r = await test_app.get("/api/agents")
        assert r.status_code == 200
        assert any(a["id"] == "default" for a in r.json())

    async def test_get_detail(self, test_app):
        r = await test_app.get("/api/agents/default")
        assert r.status_code == 200
        assert "toolsDetail" in r.json()

    async def test_create(self, test_app):
        r = await test_app.post("/api/agents", json={"id": "t1", "name": "T1"})
        assert r.status_code == 200
        assert r.json()["id"] == "t1"

    async def test_create_duplicate(self, test_app):
        await test_app.post("/api/agents", json={"id": "dup", "name": "D"})
        r = await test_app.post("/api/agents", json={"id": "dup", "name": "D"})
        assert r.status_code == 409

    async def test_update(self, test_app):
        await test_app.post("/api/agents", json={"id": "u1", "name": "Old"})
        r = await test_app.put("/api/agents/u1/config", json={"name": "New"})
        assert r.status_code == 200
        assert r.json()["name"] == "New"

    async def test_delete(self, test_app):
        await test_app.post("/api/agents", json={"id": "d1", "name": "D"})
        r = await test_app.delete("/api/agents/d1")
        assert r.status_code == 200
        r2 = await test_app.get("/api/agents/d1")
        assert r2.status_code == 404

    async def test_delete_default_forbidden(self, test_app):
        r = await test_app.delete("/api/agents/default")
        assert r.status_code == 400

    async def test_404(self, test_app):
        r = await test_app.get("/api/agents/nope")
        assert r.status_code == 404
