"""ACP Wizard API e2e：覆盖检测与安装两条 HTTP 链路。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from sensenova_claw.capabilities.miniapps.acp_wizard import ACPWizardService
from sensenova_claw.interfaces.http.config_api import router
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.platform.config.config import Config
from sensenova_claw.platform.config.config_manager import ConfigManager
from sensenova_claw.platform.secrets.store import InMemorySecretStore


async def _build_app(tmp_path: Path) -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    config_path = tmp_path / "config.yml"
    config_path.write_text(yaml.dump({
        "miniapps": {
            "default_builder": "builtin",
            "acp": {
                "enabled": False,
                "command": "",
                "args": [],
                "env": {"ACP_PROFILE": "default"},
                "startup_timeout_seconds": 20,
                "request_timeout_seconds": 180,
            },
        },
    }), encoding="utf-8")

    secret_store = InMemorySecretStore()
    cfg = Config(config_path=config_path, secret_store=secret_store)
    bus = PublicEventBus()
    config_manager = ConfigManager(config=cfg, event_bus=bus, secret_store=secret_store)

    wizard = ACPWizardService(project_root=tmp_path)
    app.state.config = cfg
    app.state.config_manager = config_manager
    app.state.secret_store = secret_store
    app.state.acp_wizard_service = wizard
    return app


@pytest.mark.asyncio
async def test_acp_wizard_api_flow_e2e(tmp_path: Path, monkeypatch) -> None:
    app = await _build_app(tmp_path)
    wizard: ACPWizardService = app.state.acp_wizard_service

    command_paths = {
        "gemini": "/usr/local/bin/gemini",
        "npm": "/usr/bin/npm",
        "uv": "/usr/bin/uv",
        "bash": "/bin/bash",
        "curl": "/usr/bin/curl",
    }
    monkeypatch.setattr(wizard, "_which", lambda command: command_paths.get(command, ""))

    executed_commands: list[list[str]] = []

    async def fake_run_command(argv: list[str]) -> tuple[str, str, int]:
        executed_commands.append(argv)
        if argv[-1] == "@openai/codex":
            command_paths["codex"] = "/usr/local/bin/codex"
        if argv[-1] == "@zed-industries/codex-acp":
            command_paths["codex-acp"] = "/usr/local/bin/codex-acp"
        return ("installed", "", 0)

    monkeypatch.setattr(wizard, "_run_command", fake_run_command)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        detect_resp = await client.get("/api/config/acp/wizard")
        assert detect_resp.status_code == 200
        detect_data = detect_resp.json()
        gemini = next(item for item in detect_data["agents"] if item["id"] == "gemini")
        codex = next(item for item in detect_data["agents"] if item["id"] == "codex")

        assert gemini["ready"] is True
        assert gemini["recommended_config"]["command"] == "/usr/local/bin/gemini"
        assert gemini["recommended_config"]["args"] == ["--experimental-acp"]
        assert codex["ready"] is False

        install_resp = await client.post("/api/config/acp/wizard/install", json={"agent_id": "codex"})
        assert install_resp.status_code == 200
        install_data = install_resp.json()

        assert install_data["ok"] is True
        assert executed_commands == [
            ["/usr/bin/npm", "install", "-g", "@openai/codex"],
            ["/usr/bin/npm", "install", "-g", "@zed-industries/codex-acp"],
        ]
        refreshed_codex = next(item for item in install_data["wizard"]["agents"] if item["id"] == "codex")
        assert refreshed_codex["ready"] is True
        assert refreshed_codex["recommended_config"]["command"] == "/usr/local/bin/codex-acp"
