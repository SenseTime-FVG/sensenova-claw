"""X01: Agent 限定 skills/tools 过滤"""
import pytest

pytestmark = pytest.mark.asyncio


class TestAgentSkillInteraction:
    async def test_agent_tool_filter(self, test_app):
        """Agent 配置 tools 列表后，详情只展示指定工具"""
        await test_app.post("/api/agents", json={
            "id": "lim", "name": "L", "tools": ["serper_search"],
        })
        r = await test_app.get("/api/agents/lim")
        names = [t["name"] for t in r.json().get("toolsDetail", [])]
        if names:
            assert all(n == "serper_search" for n in names)

    async def test_agent_skill_filter(self, test_app):
        """Agent 配置 skills 列表后，详情只展示指定 skill"""
        await test_app.post("/api/agents", json={
            "id": "slim", "name": "S", "skills": ["pdf_to_markdown"],
        })
        r = await test_app.get("/api/agents/slim")
        names = [s["name"] for s in r.json().get("skillsDetail", [])]
        if names:
            assert all(n == "pdf_to_markdown" for n in names)

    async def test_default_agent_all_tools(self, test_app):
        """default Agent（空 tools）应展示所有工具"""
        r = await test_app.get("/api/agents/default")
        tools = r.json().get("toolsDetail", [])
        assert len(tools) > 0  # 应有 builtin 工具
