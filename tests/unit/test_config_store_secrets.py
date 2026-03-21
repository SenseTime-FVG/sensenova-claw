"""config_store 的 secret-aware 写入单测。"""

from __future__ import annotations

import yaml
import pytest

from agentos.interfaces.http.config_store import persist_path_updates
from agentos.platform.config.config import Config
from agentos.platform.secrets.store import InMemorySecretStore


def test_persist_path_updates_writes_secret_ref_for_sensitive_path(tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text("tools: {}\n", encoding="utf-8")
    store = InMemorySecretStore()
    cfg = Config(config_path=config_path, secret_store=store)

    persist_path_updates(
        cfg,
        {"tools.serper_search.api_key": "sk-secret-123"},
        secret_store=store,
    )

    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["tools"]["serper_search"]["api_key"] == (
        "${secret:agentos/tools.serper_search.api_key}"
    )
    assert store.get("agentos/tools.serper_search.api_key") == "sk-secret-123"


def test_persist_path_updates_writes_plain_value_for_non_secret_path(tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text("agent: {}\n", encoding="utf-8")
    store = InMemorySecretStore()
    cfg = Config(config_path=config_path, secret_store=store)

    persist_path_updates(
        cfg,
        {"agent.model": "gpt-5.4"},
        secret_store=store,
    )

    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["agent"]["model"] == "gpt-5.4"


def test_persist_path_updates_deletes_secret_when_value_is_empty(tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "tools:\n  serper_search:\n    api_key: ${secret:agentos/tools.serper_search.api_key}\n",
        encoding="utf-8",
    )
    store = InMemorySecretStore()
    store.set("agentos/tools.serper_search.api_key", "sk-old")
    cfg = Config(config_path=config_path, secret_store=store)

    persist_path_updates(
        cfg,
        {"tools.serper_search.api_key": ""},
        secret_store=store,
    )

    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["tools"]["serper_search"]["api_key"] == ""
    assert store.get("agentos/tools.serper_search.api_key") is None


def test_persist_path_updates_skips_secret_delete_when_path_is_not_secret_ref(tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "llm:\n  providers:\n    mock:\n      api_key: ''\n",
        encoding="utf-8",
    )

    class ExplodingDeleteStore(InMemorySecretStore):
        def delete(self, ref: str) -> None:
            raise RuntimeError(f"unexpected delete: {ref}")

    store = ExplodingDeleteStore()
    cfg = Config(config_path=config_path, secret_store=store)

    persist_path_updates(
        cfg,
        {"llm.providers.mock.api_key": ""},
        secret_store=store,
    )

    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["llm"]["providers"]["mock"]["api_key"] == ""
