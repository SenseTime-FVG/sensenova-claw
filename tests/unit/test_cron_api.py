"""Cron API 单元测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentos.adapters.channels.base import Channel
from agentos.adapters.storage.repository import Repository
from agentos.interfaces.http.cron_api import router
from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.notification.service import NotificationService
from agentos.kernel.runtime.publisher import EventPublisher
from agentos.kernel.scheduler.models import CronJob, EverySchedule, SystemEventPayload, cron_job_to_db_row
from agentos.kernel.scheduler.runtime import CronRuntime
from agentos.interfaces.ws.gateway import Gateway


class DummyChannel(Channel):
    """供 API 测试使用的最小 Channel。"""

    def __init__(self, channel_id: str):
        self._channel_id = channel_id

    def get_channel_id(self) -> str:
        return self._channel_id

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send_event(self, event) -> None:
        return None


@pytest_asyncio.fixture
async def app(tmp_path):
    app = FastAPI()
    app.include_router(router)

    repo = Repository(db_path=str(tmp_path / "cron_api.db"))
    await repo.init()

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    gateway = Gateway(publisher=publisher)
    gateway.register_channel(DummyChannel("websocket"))
    notification_service = NotificationService(bus=bus)
    runtime = CronRuntime(bus=bus, repo=repo, gateway=gateway, notification_service=notification_service)
    runtime._arm_timer = lambda: None  # type: ignore[method-assign]

    app.state.services = SimpleNamespace(cron_runtime=runtime)
    app.state.repo = repo
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_create_list_get_update_delete_cron_job(client):
    create_resp = client.post("/api/cron/jobs", json={
        "name": "Daily report reminder",
        "description": "Remind me to check reports",
        "schedule_type": "cron",
        "schedule_value": "0 9 * * *",
        "timezone": "Asia/Shanghai",
        "text": "Please check the daily reports",
        "session_target": "main",
        "wake_mode": "now",
        "delete_after_run": False,
    })
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["name"] == "Daily report reminder"
    assert created["schedule_type"] == "cron"

    list_resp = client.get("/api/cron/jobs")
    assert list_resp.status_code == 200
    assert len(list_resp.json()["jobs"]) == 1

    job_id = created["id"]
    get_resp = client.get(f"/api/cron/jobs/{job_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == job_id

    update_resp = client.put(f"/api/cron/jobs/{job_id}", json={"enabled": False})
    assert update_resp.status_code == 200
    assert update_resp.json()["enabled"] is False

    delete_resp = client.delete(f"/api/cron/jobs/{job_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["success"] is True

    final_list = client.get("/api/cron/jobs")
    assert final_list.json()["jobs"] == []


def test_cron_job_delivery_fields_support_bind_update_and_clear(client, app):
    gateway = app.state.services.cron_runtime._gateway
    gateway.bind_session("sess_api_delivery", "websocket")

    create_resp = client.post("/api/cron/jobs", json={
        "name": "Delivery test",
        "schedule_type": "every",
        "schedule_value": "60000",
        "text": "notify me",
        "delivery_session_id": "sess_api_delivery",
        "notification_channels": ["browser"],
    })
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["delivery"]["session_id"] == "sess_api_delivery"
    assert created["delivery"]["channel_id"] == "websocket"
    assert created["delivery"]["notification_channels"] == ["browser"]

    job_id = created["id"]

    update_resp = client.put(f"/api/cron/jobs/{job_id}", json={
        "notification_channels": ["native"],
    })
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["delivery"]["session_id"] == "sess_api_delivery"
    assert updated["delivery"]["notification_channels"] == ["native"]

    clear_session_resp = client.put(f"/api/cron/jobs/{job_id}", json={
        "delivery_session_id": None,
        "notification_channels": ["browser"],
    })
    assert clear_session_resp.status_code == 200
    cleared = clear_session_resp.json()
    assert cleared["delivery"]["mode"] == "none"
    assert cleared["delivery"]["session_id"] is None
    assert cleared["delivery"]["notification_channels"] == ["browser"]

    remove_delivery_resp = client.put(f"/api/cron/jobs/{job_id}", json={
        "delivery_session_id": None,
        "notification_channels": [],
    })
    assert remove_delivery_resp.status_code == 200
    assert remove_delivery_resp.json()["delivery"] is None


def test_create_cron_job_rejects_unknown_delivery_session(client):
    response = client.post("/api/cron/jobs", json={
        "name": "Bad delivery",
        "schedule_type": "every",
        "schedule_value": "60000",
        "text": "notify me",
        "delivery_session_id": "sess_missing",
    })
    assert response.status_code == 400
    assert "Unknown or unbound session_id" in response.json()["detail"]


def test_trigger_cron_job_runs_immediately_without_rescheduling_disabled_job(client):
    create_resp = client.post("/api/cron/jobs", json={
        "name": "Manual trigger test",
        "schedule_type": "every",
        "schedule_value": "60000",
        "text": "run now",
        "enabled": False,
    })
    assert create_resp.status_code == 200
    job_id = create_resp.json()["id"]

    trigger_resp = client.post(f"/api/cron/jobs/{job_id}/trigger")
    assert trigger_resp.status_code == 200
    payload = trigger_resp.json()
    assert payload["success"] is True
    assert payload["deleted"] is False
    assert payload["job"]["enabled"] is False
    assert payload["job"]["last_run_status"] == "ok"
    assert payload["job"]["next_run_at_ms"] is None

    runs_resp = client.get(f"/api/cron/jobs/{job_id}/runs")
    assert runs_resp.status_code == 200
    assert len(runs_resp.json()["runs"]) == 1


def test_trigger_cron_job_returns_404_for_missing_job(client):
    response = client.post("/api/cron/jobs/cron_missing/trigger")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_cron_runs_endpoint(app):
    repo = app.state.repo

    job = CronJob(
        id="cron_run_test",
        name="Run history",
        schedule=EverySchedule(every_ms=60000),
        session_target="main",
        payload=SystemEventPayload(text="hello"),
    )
    await repo.create_cron_job(cron_job_to_db_row(job))
    await repo.insert_cron_run({
        "job_id": job.id,
        "started_at_ms": 1000,
        "ended_at_ms": 1500,
        "status": "ok",
        "error": None,
        "duration_ms": 500,
        "session_id": None,
        "delivery_status": None,
        "created_at": 1.0,
    })

    client = TestClient(app)
    response = client.get(f"/api/cron/jobs/{job.id}/runs")
    assert response.status_code == 200
    runs = response.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["status"] == "ok"
