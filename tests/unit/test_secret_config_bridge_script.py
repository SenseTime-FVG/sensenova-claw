from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / ".sensenova-claw"
        / "skills"
        / "secret-config-bridge"
        / "scripts"
        / "secret_bridge.py"
    )


def _run_secret_bridge(payload: dict, *, config_path: Path, skills_dir: Path, secret_file: Path) -> dict:
    env = {
        "HOME": str(Path.home()),
        "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
        "SENSENOVA_CLAW_SECRET_BRIDGE_CONFIG_PATH": str(config_path),
        "SENSENOVA_CLAW_SECRET_BRIDGE_SKILLS_DIR": str(skills_dir),
        "SENSENOVA_CLAW_SECRET_BRIDGE_SECRET_FILE": str(secret_file),
        "SENSENOVA_CLAW_SECRET_BRIDGE_DISABLE_KEYRING": "1",
    }
    completed = subprocess.run(
        [sys.executable, str(_script_path())],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_secret_bridge_write_updates_config_store_and_skill_mapping(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    config_path.write_text("llm:\n  providers:\n    openai:\n      api_key: \"\"\n", encoding="utf-8")
    skills_dir = tmp_path / "skills"
    (skills_dir / "openai-whisper-api").mkdir(parents=True)
    secret_file = tmp_path / "data" / "secret" / "secret.yml"

    result = _run_secret_bridge(
        {
            "action": "write",
            "json": {
                "__meta__": {
                    "skill": "openai-whisper-api",
                    "env": "OPENAI_API_KEY",
                },
                "llm": {
                    "providers": {
                        "openai": {
                            "api_key": "sk-script-write",
                        }
                    }
                },
            },
        },
        config_path=config_path,
        skills_dir=skills_dir,
        secret_file=secret_file,
    )

    assert result["ok"] is True
    assert result["secret_ref"] == "secret:openai-whisper-api:OPENAI_API_KEY"
    assert result["path"] == "llm.providers.openai.api_key"

    written_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert (
        written_config["llm"]["providers"]["openai"]["api_key"]
        == "${secret:sensenova_claw/llm.providers.openai.api_key}"
    )

    written_skill_secret = yaml.safe_load(
        (skills_dir / "openai-whisper-api" / "secret.yml").read_text(encoding="utf-8")
    )
    assert written_skill_secret == {
        "OPENAI_API_KEY": "secret:openai-whisper-api:OPENAI_API_KEY"
    }

    written_secret_store = yaml.safe_load(secret_file.read_text(encoding="utf-8"))
    assert written_secret_store["sensenova_claw/llm.providers.openai.api_key"] == "sk-script-write"
    assert written_secret_store["secret:openai-whisper-api:OPENAI_API_KEY"] == "sk-script-write"


def test_secret_bridge_read_prefers_skill_secret_mapping(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    config_path.write_text("llm:\n  providers:\n    openai:\n      api_key: fallback-value\n", encoding="utf-8")
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "openai-whisper-api"
    skill_dir.mkdir(parents=True)
    (skill_dir / "secret.yml").write_text(
        "OPENAI_API_KEY: secret:openai-whisper-api:OPENAI_API_KEY\n",
        encoding="utf-8",
    )
    secret_file = tmp_path / "data" / "secret" / "secret.yml"
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    secret_file.write_text(
        yaml.dump(
            {
                "secret:openai-whisper-api:OPENAI_API_KEY": "sk-from-secret-file",
                "sensenova_claw/llm.providers.openai.api_key": "sk-from-config-path",
            },
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    result = _run_secret_bridge(
        {
            "action": "read",
            "path": "secret:openai-whisper-api:OPENAI_API_KEY",
        },
        config_path=config_path,
        skills_dir=skills_dir,
        secret_file=secret_file,
    )

    assert result == {
        "ok": True,
        "path": "secret:openai-whisper-api:OPENAI_API_KEY",
        "value": "sk-from-secret-file",
        "source": "skill_secret_mapping",
    }
