"""CLI secret 迁移命令单测。"""

from __future__ import annotations

import argparse
import yaml

from sensenova_claw.app.main import cmd_migrate_secrets
from sensenova_claw.platform.secrets.store import InMemorySecretStore


def test_cmd_migrate_secrets_updates_config_file(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "plugins:\n"
        "  wecom:\n"
        "    secret: plain-wecom-secret\n",
        encoding="utf-8",
    )
    secret_store = InMemorySecretStore()
    monkeypatch.setattr("sensenova_claw.app.main.KeyringSecretStore", lambda: secret_store)

    exit_code = cmd_migrate_secrets(argparse.Namespace(config=str(config_path)))

    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert written["plugins"]["wecom"]["secret"] == "${secret:sensenova_claw/plugins.wecom.secret}"
    assert secret_store.get("sensenova_claw/plugins.wecom.secret") == "plain-wecom-secret"
