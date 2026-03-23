from __future__ import annotations

import copy
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from sensenova_claw.capabilities.tools.builtin import (
    BaiduSearchTool,
    BraveSearchTool,
    SerperSearchTool,
    TavilySearchTool,
)
from sensenova_claw.platform.config.config import config


@pytest.fixture(autouse=True)
def restore_config():
    original = copy.deepcopy(config.data)
    yield
    config.data = original


def _make_http_response(payload: dict) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def _make_async_client(method_name: str, response: MagicMock) -> tuple[MagicMock, MagicMock]:
    client = MagicMock()
    setattr(client, method_name, AsyncMock(return_value=response))
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=client)
    manager.__aexit__ = AsyncMock(return_value=None)
    return manager, client


@pytest.mark.asyncio
async def test_serper_search_without_api_key_returns_empty_result() -> None:
    config.data["tools"]["serper_search"]["api_key"] = ""

    tool = SerperSearchTool()
    result = await tool.execute(q="Sensenova-Claw")

    assert result["provider"] == "serper"
    assert result["query"] == "Sensenova-Claw"
    assert result["items"] == []
    assert "SERPER_API_KEY" in result["note"]


@pytest.mark.asyncio
async def test_brave_search_maps_response() -> None:
    config.data["tools"]["brave_search"]["api_key"] = "brave-test"
    config.data["tools"]["brave_search"]["max_results"] = 3

    response = _make_http_response({
        "query": {"original": "Sensenova-Claw", "more_results_available": True},
        "web": {
            "results": [
                {
                    "title": "Sensenova-Claw",
                    "url": "https://example.com/sensenova_claw",
                    "description": "Main snippet",
                    "extra_snippets": ["Extra snippet 1", "Extra snippet 2"],
                    "language": "en",
                }
            ]
        },
    })
    manager, client = _make_async_client("get", response)

    tool = BraveSearchTool()
    with patch("sensenova_claw.capabilities.tools.builtin.httpx.AsyncClient", return_value=manager):
        result = await tool.execute(q="Sensenova-Claw", page=2, freshness="pw", extra_snippets=True)

    client.get.assert_awaited_once_with(
        "https://api.search.brave.com/res/v1/web/search",
        headers={
            "X-Subscription-Token": "brave-test",
            "Accept": "application/json",
        },
        params={
            "q": "Sensenova-Claw",
            "count": 3,
            "offset": 1,
            "country": "US",
            "search_lang": "en",
            "ui_lang": "en-US",
            "freshness": "pw",
            "extra_snippets": "true",
        },
    )
    assert result["provider"] == "brave"
    assert result["query"] == "Sensenova-Claw"
    assert result["more_results_available"] is True
    assert result["items"][0]["title"] == "Sensenova-Claw"
    assert result["items"][0]["link"] == "https://example.com/sensenova_claw"
    assert "Main snippet" in result["items"][0]["snippet"]
    assert "Extra snippet 1" in result["items"][0]["snippet"]


@pytest.mark.asyncio
async def test_baidu_search_maps_response() -> None:
    config.data["tools"]["baidu_search"]["api_key"] = "baidu-test"

    response = _make_http_response({
        "request_id": "req-baidu",
        "references": [
            {
                "type": "web",
                "title": "百度千帆",
                "url": "https://cloud.baidu.com",
                "content": "平台介绍",
                "date": "2025-05-23 00:00:00",
                "website": "百度智能云",
                "authority_score": 0.91,
                "rerank_score": 0.88,
            },
            {
                "type": "video",
                "title": "ignored",
                "url": "https://example.com/video",
                "content": "video",
            },
        ],
    })
    manager, client = _make_async_client("post", response)

    tool = BaiduSearchTool()
    with patch("sensenova_claw.capabilities.tools.builtin.httpx.AsyncClient", return_value=manager):
        result = await tool.execute(q="百度千帆", max_results=5, search_recency_filter="month")

    client.post.assert_awaited_once_with(
        "https://qianfan.baidubce.com/v2/ai_search/web_search",
        headers={
            "X-Appbuilder-Authorization": "Bearer baidu-test",
            "Content-Type": "application/json",
        },
        json={
            "messages": [{"role": "user", "content": "百度千帆"}],
            "search_source": "baidu_search_v2",
            "resource_type_filter": [{"type": "web", "top_k": 5}],
            "search_recency_filter": "month",
        },
    )
    assert result["provider"] == "baidu"
    assert result["request_id"] == "req-baidu"
    assert len(result["items"]) == 1
    assert result["items"][0]["title"] == "百度千帆"
    assert result["items"][0]["website"] == "百度智能云"


@pytest.mark.asyncio
async def test_tavily_search_maps_response() -> None:
    config.data["tools"]["tavily_search"]["api_key"] = "tavily-test"
    config.data["tools"]["tavily_search"]["project_id"] = "project-123"

    response = _make_http_response({
        "query": "Sensenova-Claw",
        "answer": "Sensenova-Claw is an event-driven AI agent platform.",
        "results": [
            {
                "title": "Sensenova-Claw Docs",
                "url": "https://example.com/docs",
                "content": "Sensenova-Claw documentation",
                "score": 0.97,
                "favicon": "https://example.com/favicon.ico",
            }
        ],
        "response_time": "0.91",
        "request_id": "req-tavily",
    })
    manager, client = _make_async_client("post", response)

    tool = TavilySearchTool()
    with patch("sensenova_claw.capabilities.tools.builtin.httpx.AsyncClient", return_value=manager):
        result = await tool.execute(q="Sensenova-Claw", topic="news", time_range="week", max_results=4)

    client.post.assert_awaited_once_with(
        "https://api.tavily.com/search",
        headers={
            "Authorization": "Bearer tavily-test",
            "Content-Type": "application/json",
            "X-Project-ID": "project-123",
        },
        json={
            "query": "Sensenova-Claw",
            "search_depth": "basic",
            "topic": "news",
            "max_results": 4,
            "time_range": "week",
        },
    )
    assert result["provider"] == "tavily"
    assert result["answer"] == "Sensenova-Claw is an event-driven AI agent platform."
    assert result["request_id"] == "req-tavily"
    assert result["items"][0]["title"] == "Sensenova-Claw Docs"
