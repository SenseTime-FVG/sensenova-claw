"""Proactive recommendations API 单元测试。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock

from sensenova_claw.interfaces.http.proactive_api import router


@pytest.fixture
def mock_runtime():
    rt = MagicMock()
    rt.list_jobs = AsyncMock(return_value=[])
    return rt


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.list_pending_recommendations = AsyncMock(return_value=[
        {
            "job_id": "builtin-turn-end-recommendation",
            "job_name": "会话推荐",
            "session_id": "sess_source_001",
            "source_session_id": "sess_source_001",
            "recommendation_type": "turn_end",
            "received_at_ms": 1710000100000,
            "items": [
                {
                    "id": "rec_1",
                    "title": "继续追问竞争对手",
                    "prompt": "请继续分析三个最强竞争对手",
                    "category": "follow-up",
                },
            ],
        },
    ])
    return repo


@pytest.fixture
def app(mock_runtime, mock_repo):
    app = FastAPI()
    app.include_router(router)
    app.state.services = MagicMock()
    app.state.services.proactive_runtime = mock_runtime
    app.state.services.repo = mock_repo
    return app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_list_pending_recommendations(client, mock_repo):
    response = await client.get("/api/proactive/recommendations?limit=5")

    assert response.status_code == 200
    assert response.json()["recommendations"][0]["items"][0]["id"] == "rec_1"
    mock_repo.list_pending_recommendations.assert_called_once_with(limit=5)
