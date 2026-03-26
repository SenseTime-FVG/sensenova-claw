"""Proactive trigger API 单元测试。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from sensenova_claw.interfaces.http.proactive_api import router


@pytest.fixture
def mock_runtime():
    rt = MagicMock()
    rt.trigger_job = AsyncMock()
    return rt


@pytest.fixture
def app(mock_runtime):
    app = FastAPI()
    app.include_router(router)
    app.state.services = MagicMock()
    app.state.services.proactive_runtime = mock_runtime
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_trigger_job_success(client, mock_runtime):
    """测试成功触发 job。"""
    mock_runtime.trigger_job.return_value = None

    response = client.post("/api/proactive/jobs/test-job/trigger", json={"session_id": None})

    assert response.status_code == 200
    assert response.json() == {"status": "triggered", "job_id": "test-job"}
    mock_runtime.trigger_job.assert_called_once_with("test-job", None)


def test_trigger_job_not_found(client, mock_runtime):
    """测试 job 不存在返回 404。"""
    mock_runtime.trigger_job.side_effect = ValueError("Job not found: test-job")

    response = client.post("/api/proactive/jobs/test-job/trigger", json={"session_id": None})

    assert response.status_code == 404


def test_trigger_job_disabled(client, mock_runtime):
    """测试 job 已禁用返回 400。"""
    mock_runtime.trigger_job.side_effect = ValueError("Job is disabled: test-job")

    response = client.post("/api/proactive/jobs/test-job/trigger", json={"session_id": None})

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "job_disabled"


def test_trigger_job_running(client, mock_runtime):
    """测试 job 正在运行返回 409。"""
    mock_runtime.trigger_job.side_effect = ValueError("Job is already running: test-job")

    response = client.post("/api/proactive/jobs/test-job/trigger", json={"session_id": None})

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "job_running"
