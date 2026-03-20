"""Config 的 secret 解析单测。"""

from __future__ import annotations

import pytest

from agentos.platform.config.config import Config
from agentos.platform.secrets.store import InMemorySecretStore, SecretStoreError


def test_config_resolves_secret_reference(tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "llm:\n"
        "  providers:\n"
        "    openai:\n"
        "      api_key: ${secret:agentos/llm.providers.openai.api_key}\n",
        encoding="utf-8",
    )
    store = InMemorySecretStore()
    store.set("agentos/llm.providers.openai.api_key", "sk-from-secret-store")

    cfg = Config(config_path=config_path, secret_store=store)

    assert cfg.get("llm.providers.openai.api_key") == "sk-from-secret-store"


def test_config_raises_when_secret_lookup_fails(tmp_path):
    class BrokenStore:
        def get(self, ref: str) -> str | None:
            raise SecretStoreError("读取 secret 失败")

    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "tools:\n"
        "  serper_search:\n"
        "    api_key: ${secret:agentos/tools.serper_search.api_key}\n",
        encoding="utf-8",
    )

    with pytest.raises(SecretStoreError, match="读取 secret 失败"):
        Config(config_path=config_path, secret_store=BrokenStore())
