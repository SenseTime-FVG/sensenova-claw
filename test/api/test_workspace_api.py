"""Workspace API 端点测试"""
import pytest

pytestmark = pytest.mark.asyncio


class TestWorkspaceAPI:
    async def test_list_files(self, test_app):
        r = await test_app.get("/api/workspace/files")
        assert r.status_code == 200

    async def test_write_read(self, test_app):
        await test_app.put("/api/workspace/files/TEST.md", json={"content": "# T"})
        r = await test_app.get("/api/workspace/files/TEST.md")
        assert r.status_code == 200

    async def test_reject_non_md(self, test_app):
        r = await test_app.get("/api/workspace/files/x.txt")
        assert r.status_code == 400

    async def test_delete_core_forbidden(self, test_app):
        r = await test_app.delete("/api/workspace/files/AGENTS.md")
        assert r.status_code == 403

    async def test_write_non_md_rejected(self, test_app):
        r = await test_app.put("/api/workspace/files/bad.py", json={"content": "print(1)"})
        assert r.status_code == 400
