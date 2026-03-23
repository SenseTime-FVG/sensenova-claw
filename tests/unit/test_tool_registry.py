"""T04: ToolRegistry 注册/发现"""
from unittest.mock import patch

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

    def test_email_tools_not_registered_by_default(self):
        """email 工具默认不注册（tools.email.enabled=False）"""
        r = ToolRegistry()
        names = {t["name"] for t in r.as_llm_tools()}
        email_tools = {"send_email", "list_emails", "read_email", "download_attachment", "mark_email", "search_emails"}
        assert email_tools.isdisjoint(names)

    def test_email_tools_registered_when_enabled(self):
        """tools.email.enabled=True 时 email 工具应注册"""
        from agentos.platform.config.config import config
        original = config.data["tools"]["email"]["enabled"]
        try:
            config.data["tools"]["email"]["enabled"] = True
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
        finally:
            config.data["tools"]["email"]["enabled"] = original

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
