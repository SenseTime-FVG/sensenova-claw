from __future__ import annotations

import copy

import pytest

from agentos.capabilities.tools.builtin import (
    BaiduSearchTool,
    BraveSearchTool,
    TavilySearchTool,
)
from agentos.platform.config.config import config


@pytest.fixture(autouse=True)
def restore_config():
    original = copy.deepcopy(config.data)
    yield
    config.data = original


def _skip_if_api_key_missing(tool_name: str) -> None:
    if not config.get(f"tools.{tool_name}.api_key", ""):
        pytest.skip(f"{tool_name} API key 未配置，跳过真实搜索测试")


@pytest.mark.asyncio
@pytest.mark.slow
async def test_brave_search_live_returns_results() -> None:
    _skip_if_api_key_missing("brave_search")

    tool = BraveSearchTool()
    result = await tool.execute(q="OpenAI", count=3)

    assert result["provider"] == "brave"
    assert isinstance(result["items"], list)
    assert result["items"], "Brave Search 应返回至少一条结果"
    assert result["items"][0]["title"]
    assert result["items"][0]["link"]


@pytest.mark.asyncio
@pytest.mark.slow
async def test_baidu_search_live_returns_results() -> None:
    _skip_if_api_key_missing("baidu_search")

    tool = BaiduSearchTool()
    result = await tool.execute(q="百度千帆", max_results=3)

    assert result["provider"] == "baidu"
    assert isinstance(result["items"], list)
    assert result["items"], "百度搜索应返回至少一条结果"
    assert result["items"][0]["title"]
    assert result["items"][0]["link"]


@pytest.mark.asyncio
@pytest.mark.slow
async def test_tavily_search_live_returns_results() -> None:
    _skip_if_api_key_missing("tavily_search")

    tool = TavilySearchTool()
    result = await tool.execute(q="OpenAI", max_results=3, topic="news")

    assert result["provider"] == "tavily"
    assert isinstance(result["items"], list)
    assert result["items"], "Tavily Search 应返回至少一条结果"
    assert result["items"][0]["title"]
    assert result["items"][0]["link"]
