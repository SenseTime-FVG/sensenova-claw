from __future__ import annotations

import sys

import pytest

from sensenova_claw.capabilities.miniapps.acp_wizard import ACPWizardService


def test_inspect_detects_supported_agents_and_recommended_config(monkeypatch) -> None:
    service = ACPWizardService(project_root=".")
    service._platform = "windows"

    resolved = {
        "codex": "C:/Tools/codex.cmd",
        "codex-acp": "C:/Tools/codex-acp.cmd",
        "claude-agent-acp": "",
        "gemini": "C:/Tools/gemini.cmd",
        "kimi": "",
        "opencode": "C:/Tools/opencode.cmd",
        "npm": "C:/Program Files/nodejs/npm.cmd",
        "uv": "C:/Users/test/.local/bin/uv.exe",
        "powershell": "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
        "pwsh": "",
        "brew": "",
        "bash": "",
        "curl": "",
        "python3": "",
        "python": "C:/Python/python.exe",
    }
    monkeypatch.setattr(service, "_which", lambda command: resolved.get(command, ""))

    data = service.inspect(current_config={"command": "codex-acp", "args": []})

    assert data["platform"]["id"] == "windows"
    codex = next(item for item in data["agents"] if item["id"] == "codex")
    gemini = next(item for item in data["agents"] if item["id"] == "gemini")
    opencode = next(item for item in data["agents"] if item["id"] == "opencode")

    assert codex["ready"] is True
    assert codex["configured"] is True
    assert codex["recommended_config"]["command"] == "C:/Tools/codex-acp.cmd"
    assert codex["install_steps"][0]["installed"] is True
    assert codex["install_steps"][1]["installed"] is True

    assert gemini["recommended_config"]["command"] == "C:/Tools/gemini.cmd"
    assert gemini["recommended_config"]["args"] == ["--experimental-acp"]
    assert gemini["ready"] is True

    assert opencode["recommended_config"]["args"] == ["acp"]
    assert opencode["install_steps"][0]["command_preview"] == "'C:/Program Files/nodejs/npm.cmd' install -g opencode-ai"


@pytest.mark.asyncio
async def test_install_chooses_platform_specific_recipe(monkeypatch) -> None:
    service = ACPWizardService(project_root=".")
    service._platform = "windows"

    resolved = {
        "npm": "",
        "uv": "",
        "powershell": "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
        "pwsh": "",
        "bash": "",
        "curl": "",
        "kimi": "",
    }
    monkeypatch.setattr(service, "_which", lambda command: resolved.get(command, ""))

    captured: list[list[str]] = []

    async def fake_run_command(argv: list[str]) -> tuple[str, str, int]:
        captured.append(argv)
        return ("ok", "", 0)

    monkeypatch.setattr(service, "_run_command", fake_run_command)

    result = await service.install("kimi")

    assert result["ok"] is True
    assert captured == [[
        "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "Invoke-RestMethod https://code.kimi.com/install.ps1 | Invoke-Expression",
    ]]


@pytest.mark.asyncio
async def test_install_uses_detected_pwsh_binary(monkeypatch) -> None:
    service = ACPWizardService(project_root=".")
    service._platform = "windows"

    resolved = {
        "npm": "",
        "uv": "",
        "powershell": "C:/Program Files/PowerShell/7/pwsh.exe",
        "pwsh": "C:/Program Files/PowerShell/7/pwsh.exe",
        "bash": "",
        "curl": "",
        "kimi": "",
    }
    monkeypatch.setattr(service, "_which", lambda command: resolved.get(command, ""))

    captured: list[list[str]] = []

    async def fake_run_command(argv: list[str]) -> tuple[str, str, int]:
        captured.append(argv)
        return ("ok", "", 0)

    monkeypatch.setattr(service, "_run_command", fake_run_command)

    result = await service.install("kimi")

    assert result["ok"] is True
    assert captured == [[
        "C:/Program Files/PowerShell/7/pwsh.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "Invoke-RestMethod https://code.kimi.com/install.ps1 | Invoke-Expression",
    ]]


def test_codex_bridge_uses_python_runtime(monkeypatch) -> None:
    service = ACPWizardService(project_root=".")
    python_path = sys.executable
    resolved = {
        "codex": "/usr/local/bin/codex",
        "npm": "/usr/bin/npm",
        "uv": "/usr/bin/uv",
        "brew": "",
        "bash": "/bin/bash",
        "curl": "/usr/bin/curl",
        "powershell": "",
        "pwsh": "",
        python_path: python_path,
        "python3": "/usr/bin/python3",
        "python": "",
    }
    monkeypatch.setattr(service, "_which", lambda command: resolved.get(command, ""))

    data = service.inspect()
    bridge = next(item for item in data["agents"] if item["id"] == "codex-bridge")

    assert bridge["ready"] is True
    assert bridge["recommended_config"]["command"] == python_path
    assert bridge["recommended_config"]["args"] == [
        "-m",
        "sensenova_claw.capabilities.miniapps.codex_acp_bridge",
    ]
