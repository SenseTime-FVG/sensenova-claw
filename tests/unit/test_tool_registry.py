"""T04: ToolRegistry 注册/发现"""
from agentos.capabilities.tools.registry import ToolRegistry
from agentos.capabilities.tools.base import Tool, ToolRiskLevel


class MockTool(Tool):
    name = "mock_tool"
    description = "A mock tool"
    parameters = {"type": "object", "properties": {}, "required": []}
    risk_level = ToolRiskLevel.LOW

    async def execute(self, **kwargs):
        return {"ok": True}


class TestToolRegistry:
    def test_builtin_registered(self):
        r = ToolRegistry()
        assert r.get("bash_command") is not None
        assert r.get("serper_search") is not None
        assert r.get("fetch_url") is not None
        assert r.get("read_file") is not None
        assert r.get("write_file") is not None
        assert r.get("ask_user") is not None

    def test_email_tools_registered(self):
        r = ToolRegistry()
        names = {t["name"] for t in r.as_llm_tools()}
        assert {
            "send_email",
            "list_emails",
            "read_email",
            "download_attachment",
            "mark_email",
            "search_emails",
        }.issubset(names)

    def test_register_custom(self):
        r = ToolRegistry()
        r.register(MockTool())
        assert r.get("mock_tool") is not None
        assert r.get("mock_tool").description == "A mock tool"

    def test_get_nonexist(self):
        r = ToolRegistry()
        assert r.get("nope") is None

    def test_as_llm_tools(self):
        r = ToolRegistry()
        tools = r.as_llm_tools()
        assert len(tools) >= 5
        names = [t["name"] for t in tools]
        assert "bash_command" in names
        for t in tools:
            assert "name" in t
            assert "description" in t
            assert "parameters" in t
