"""Sessions API 单测。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sensenova_claw.adapters.storage.repository import Repository
from sensenova_claw.adapters.storage.session_jsonl import SessionJsonlWriter
from sensenova_claw.interfaces.http.sessions import router
from sensenova_claw.interfaces.ws.gateway import Gateway
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.runtime.publisher import EventPublisher


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def app(tmp_path):
    app = FastAPI()
    app.include_router(router)

    sensenova_claw_home = tmp_path / ".sensenova-claw"
    sensenova_claw_home.mkdir()

    repo = Repository(db_path=str(tmp_path / "test.db"))
    _run(repo.init())

    bus = PublicEventBus()
    publisher = EventPublisher(bus)
    gateway = Gateway(publisher=publisher, repo=repo)

    @dataclass
    class Services:
        repo: Repository
        gateway: Gateway

    app.state.services = Services(repo=repo, gateway=gateway)
    app.state.sensenova_claw_home = str(sensenova_claw_home)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_delete_session_removes_db_rows_and_jsonl_file(client, app):
    _run(app.state.services.repo.create_session("sess_delete_1", meta={"agent_id": "helper"}))
    _run(app.state.services.repo.create_turn("turn_delete_1", "sess_delete_1", "hello"))
    _run(app.state.services.repo.save_message("sess_delete_1", "turn_delete_1", "user", content="hello"))

    writer = SessionJsonlWriter(base_dir=app.state.sensenova_claw_home + "/agents")
    writer.append("helper", "sess_delete_1", "turn_delete_1", {"role": "user", "content": "hello"})

    resp = client.delete("/api/sessions/sess_delete_1")

    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted", "session_id": "sess_delete_1"}
    assert _run(app.state.services.repo.get_session_meta("sess_delete_1")) is None
    assert writer._session_path("helper", "sess_delete_1").exists() is False


def test_delete_session_defaults_to_default_agent_dir_when_meta_missing(client, app):
    _run(app.state.services.repo.create_session("sess_delete_default"))

    writer = SessionJsonlWriter(base_dir=app.state.sensenova_claw_home + "/agents")
    writer.append("default", "sess_delete_default", "turn_1", {"role": "user", "content": "hello"})

    resp = client.delete("/api/sessions/sess_delete_default")

    assert resp.status_code == 200
    assert writer._session_path("default", "sess_delete_default").exists() is False


def test_delete_session_missing_returns_404(client):
    resp = client.delete("/api/sessions/missing_session")

    assert resp.status_code == 404


def test_list_sessions_hides_hidden_by_default(client, app):
    _run(app.state.services.repo.create_session("sess_visible", meta={"title": "Visible"}))
    _run(app.state.services.repo.create_session(
        "sess_hidden",
        meta={"title": "Hidden Scratch", "visibility": "hidden"},
    ))

    resp = client.get("/api/sessions")

    assert resp.status_code == 200
    session_ids = {item["session_id"] for item in resp.json()["sessions"]}
    assert "sess_visible" in session_ids
    assert "sess_hidden" not in session_ids


def test_list_sessions_include_hidden_returns_hidden_sessions(client, app):
    _run(app.state.services.repo.create_session("sess_visible", meta={"title": "Visible"}))
    _run(app.state.services.repo.create_session(
        "sess_hidden",
        meta={"title": "Hidden Scratch", "visibility": "hidden"},
    ))

    resp = client.get("/api/sessions?include_hidden=1")

    assert resp.status_code == 200
    session_ids = {item["session_id"] for item in resp.json()["sessions"]}
    assert "sess_visible" in session_ids
    assert "sess_hidden" in session_ids


def test_bulk_delete_sessions_by_ids(client, app):
    _run(app.state.services.repo.create_session("sess_batch_1", meta={"agent_id": "helper"}))
    _run(app.state.services.repo.create_session("sess_batch_2"))

    writer = SessionJsonlWriter(base_dir=app.state.sensenova_claw_home + "/agents")
    writer.append("helper", "sess_batch_1", "turn_1", {"role": "user", "content": "1"})
    writer.append("default", "sess_batch_2", "turn_1", {"role": "user", "content": "2"})

    resp = client.post("/api/sessions/bulk-delete", json={
        "session_ids": ["sess_batch_1", "sess_batch_2"],
    })

    assert resp.status_code == 200
    assert resp.json()["deleted_count"] == 2
    assert set(resp.json()["deleted_session_ids"]) == {"sess_batch_1", "sess_batch_2"}
    assert writer._session_path("helper", "sess_batch_1").exists() is False
    assert writer._session_path("default", "sess_batch_2").exists() is False


def test_bulk_delete_sessions_by_filter(client, app):
    _run(app.state.services.repo.create_session("sess_filter_1", meta={"title": "Alpha Research", "agent_id": "helper"}))
    _run(app.state.services.repo.create_session("sess_filter_2", meta={"title": "Alpha Review"}))
    _run(app.state.services.repo.create_session("sess_filter_3", meta={"title": "Beta Review"}))

    conn = app.state.services.repo._conn()
    conn.execute("UPDATE sessions SET status = 'closed' WHERE session_id = 'sess_filter_2'")
    conn.execute("UPDATE sessions SET status = 'closed' WHERE session_id = 'sess_filter_3'")
    conn.commit()
    conn.close()

    writer = SessionJsonlWriter(base_dir=app.state.sensenova_claw_home + "/agents")
    writer.append("helper", "sess_filter_1", "turn_1", {"role": "user", "content": "1"})
    writer.append("default", "sess_filter_2", "turn_1", {"role": "user", "content": "2"})
    writer.append("default", "sess_filter_3", "turn_1", {"role": "user", "content": "3"})

    resp = client.post("/api/sessions/bulk-delete", json={
        "filter": {
            "search_term": "Alpha",
            "status": "closed",
        },
    })

    assert resp.status_code == 200
    assert resp.json()["deleted_count"] == 1
    assert resp.json()["deleted_session_ids"] == ["sess_filter_2"]
    assert writer._session_path("default", "sess_filter_2").exists() is False
    assert writer._session_path("helper", "sess_filter_1").exists() is True
    assert writer._session_path("default", "sess_filter_3").exists() is True
