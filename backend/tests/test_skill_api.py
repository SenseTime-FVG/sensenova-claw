"""Skills API 端点单测（使用 TestClient + mock service）"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.skills import router
from app.skills.models import SearchResult, SkillSearchItem
from app.skills.registry import Skill, SkillRegistry


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)

    # mock skill_registry
    mock_skill = MagicMock(spec=Skill)
    mock_skill.name = "test-skill"
    mock_skill.description = "Test skill"
    mock_skill.path = "/fake/path"
    mock_skill.source = "local"
    mock_skill.version = None
    mock_skill.install_info = None

    registry = MagicMock(spec=SkillRegistry)
    registry.get_all.return_value = [mock_skill]
    registry.get.return_value = mock_skill
    registry.is_enabled.return_value = True

    app.state.skill_registry = registry
    app.state.config = MagicMock()
    app.state.config.data = {}

    # mock market_service
    market_service = AsyncMock()
    market_service.search.return_value = SearchResult(
        source="clawhub", total=1, page=1, page_size=20,
        items=[SkillSearchItem(id="x", name="x", description="X", source="clawhub")],
    )
    market_service.install.return_value = {"ok": True, "skill_name": "x"}
    market_service.uninstall.return_value = {"ok": True}
    market_service.check_updates.return_value = []
    market_service.update.return_value = {"ok": True, "old_version": "1.0", "new_version": "1.1"}

    app.state.market_service = market_service
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_list_skills(client):
    resp = client.get("/api/skills")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "test-skill"
    assert "source" in data[0]
    assert "enabled" in data[0]


def test_market_search(client):
    resp = client.get("/api/skills/market/search?source=clawhub&q=test")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1


def test_install(client):
    resp = client.post("/api/skills/install", json={"source": "clawhub", "id": "x"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_uninstall(client):
    resp = client.delete("/api/skills/test-skill")
    assert resp.status_code == 200


def test_toggle_enabled(client):
    resp = client.patch("/api/skills/test-skill", json={"enabled": False})
    assert resp.status_code == 200


def test_check_updates(client):
    resp = client.post("/api/skills/check-updates")
    assert resp.status_code == 200
    assert "updates" in resp.json()


def test_update_skill(client):
    resp = client.post("/api/skills/test-skill/update")
    assert resp.status_code == 200
