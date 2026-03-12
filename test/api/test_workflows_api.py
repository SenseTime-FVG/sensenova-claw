"""W04: Workflow API 全部端点"""
import pytest

pytestmark = pytest.mark.asyncio


class TestWorkflowsAPI:
    async def test_list(self, test_app):
        r = await test_app.get("/api/workflows")
        assert r.status_code == 200

    async def test_create(self, test_app):
        r = await test_app.post("/api/workflows", json={
            "id": "tw", "name": "TW",
            "nodes": [{"id": "n1"}, {"id": "n2"}],
            "edges": [{"from_node": "n1", "to_node": "n2"}],
            "entry_node": "n1", "exit_nodes": ["n2"],
        })
        assert r.status_code == 200

    async def test_create_duplicate(self, test_app):
        await test_app.post("/api/workflows", json={
            "id": "tw_dup", "name": "TD",
            "nodes": [{"id": "n1"}], "edges": [],
        })
        r = await test_app.post("/api/workflows", json={
            "id": "tw_dup", "name": "TD",
            "nodes": [{"id": "n1"}], "edges": [],
        })
        assert r.status_code == 409

    async def test_get(self, test_app):
        await test_app.post("/api/workflows", json={
            "id": "g1", "name": "G",
            "nodes": [{"id": "n1"}], "edges": [],
        })
        r = await test_app.get("/api/workflows/g1")
        assert r.status_code == 200

    async def test_delete(self, test_app):
        await test_app.post("/api/workflows", json={
            "id": "del1", "name": "D",
            "nodes": [{"id": "n1"}], "edges": [],
        })
        r = await test_app.delete("/api/workflows/del1")
        assert r.status_code == 200

    async def test_404(self, test_app):
        r = await test_app.get("/api/workflows/nope")
        assert r.status_code == 404
