"""Tool API 端点测试"""
import pytest

pytestmark = pytest.mark.asyncio


class TestToolsAPI:
    async def test_list(self, test_app):
        r = await test_app.get("/api/tools")
        assert r.status_code == 200
        tools = r.json()
        assert isinstance(tools, list)
        names = [t["name"] for t in tools]
        assert "bash_command" in names
        assert "read_file" in names
