"""明文 secret 迁移单测。"""

from __future__ import annotations

import yaml

from agentos.platform.config.config import Config
from agentos.platform.secrets.migration import migrate_plaintext_secrets
from agentos.platform.secrets.store import InMemorySecretStore


def test_migrate_plaintext_secrets_moves_plain_values_to_secret_store(tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "llm:\n"
        "  providers:\n"
        "    openai:\n"
        "      api_key: sk-openai-123\n"
        "tools:\n"
        "  serper_search:\n"
        "    api_key: sk-serper-456\n",
        encoding="utf-8",
    )
    store = InMemorySecretStore()
    cfg = Config(config_path=config_path, secret_store=store)

    report = migrate_plaintext_secrets(cfg, secret_store=store)

    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["llm"]["providers"]["openai"]["api_key"] == (
        "${secret:agentos/llm.providers.openai.api_key}"
    )
    assert written["tools"]["serper_search"]["api_key"] == (
        "${secret:agentos/tools.serper_search.api_key}"
    )
    assert store.get("agentos/llm.providers.openai.api_key") == "sk-openai-123"
    assert store.get("agentos/tools.serper_search.api_key") == "sk-serper-456"
    assert report["migrated"] == 2
    assert "llm.providers.openai.api_key" in report["migrated_paths"]


def test_migrate_plaintext_secrets_skips_env_and_existing_secret_refs(tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "llm:\n"
        "  providers:\n"
        "    openai:\n"
        "      api_key: ${OPENAI_API_KEY}\n"
        "tools:\n"
        "  tavily_search:\n"
        "    api_key: ${secret:agentos/tools.tavily_search.api_key}\n",
        encoding="utf-8",
    )
    store = InMemorySecretStore()
    cfg = Config(config_path=config_path, secret_store=store)

    report = migrate_plaintext_secrets(cfg, secret_store=store)

    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["llm"]["providers"]["openai"]["api_key"] == "${OPENAI_API_KEY}"
    assert written["tools"]["tavily_search"]["api_key"] == (
        "${secret:agentos/tools.tavily_search.api_key}"
    )
    assert report["migrated"] == 0
