"""secret 迁移 API 单测。"""

from __future__ import annotations

import yaml

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentos.interfaces.http.config_api import router
from agentos.platform.config.config import Config
from agentos.platform.secrets.store import InMemorySecretStore


def test_migrate_secrets_endpoint_migrates_plaintext_values(tmp_path):
    app = FastAPI()
    app.include_router(router)

    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "plugins:\n"
        "  feishu:\n"
        "    app_secret: plain-feishu-secret\n",
        encoding="utf-8",
    )
    secret_store = InMemorySecretStore()
    app.state.config = Config(config_path=config_path, secret_store=secret_store)
    app.state.secret_store = secret_store

    client = TestClient(app)
    response = client.post("/api/config/migrate-secrets")

    assert response.status_code == 200
    body = response.json()
    assert body["migrated"] == 1
    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["plugins"]["feishu"]["app_secret"] == (
        "${secret:agentos/plugins.feishu.app_secret}"
    )
