"""T04: ToolRegistry 注册/发现"""
import copy

import pytest

from agentos.capabilities.tools.registry import ToolRegistry
from agentos.capabilities.tools.base import Tool, ToolRiskLevel
from agentos.platform.config.config import config


class MockTool(Tool):
    name = "mock_tool"
    description = "A mock tool"
    parameters = {"type": "object", "properties": {}, "required": []}
    risk_level = ToolRiskLevel.LOW

    async def execute(self, **kwargs):
        return {"ok": True}


@pytest.fixture(autouse=True)
def restore_config():
    original = copy.deepcopy(config.data)
    yield
    config.data = original


class TestToolRegistry:
    def test_builtin_registered(self):
        r = ToolRegistry()
        assert r.get("bash_command") is not None
        assert r.get("serper_search") is not None
        assert r.get("brave_search") is not None
        assert r.get("baidu_search") is not None
        assert r.get("tavily_search") is not None
        assert r.get("fetch_url") is not None
        assert r.get("read_file") is not None
        assert r.get("write_file") is not None

    def test_register_custom(self):
        r = ToolRegistry()
        r.register(MockTool())
        assert r.get("mock_tool") is not None
        assert r.get("mock_tool").description == "A mock tool"

    def test_get_nonexist(self):
        r = ToolRegistry()
        assert r.get("nope") is None

    def test_as_llm_tools(self):
        config.data["agent"]["provider"] = "mock"
        r = ToolRegistry()
        tools = r.as_llm_tools()
        assert len(tools) >= 8
        names = [t["name"] for t in tools]
        assert "bash_command" in names
        assert "brave_search" in names
        assert "baidu_search" in names
        assert "tavily_search" in names
        for t in tools:
            assert "name" in t
            assert "description" in t
            assert "parameters" in t

    def test_as_llm_tools_hides_unconfigured_search_tools_for_real_provider(self):
        config.data["agent"]["provider"] = "openai"
        config.data["tools"]["brave_search"]["api_key"] = ""
        config.data["tools"]["baidu_search"]["api_key"] = ""
        config.data["tools"]["tavily_search"]["api_key"] = ""

        r = ToolRegistry()
        names = [tool["name"] for tool in r.as_llm_tools()]

        assert "brave_search" not in names
        assert "baidu_search" not in names
        assert "tavily_search" not in names
