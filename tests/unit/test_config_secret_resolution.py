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
        def is_available(self) -> bool:
            return True

        def get(self, ref: str) -> str | None:
            raise SecretStoreError("读取 secret 失败")

    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "tools:\n"
        "  serper_search:\n"
        "    api_key: ${secret:agentos/tools.serper_search.api_key}\n",
        encoding="utf-8",
    )

    cfg = Config(config_path=config_path, secret_store=BrokenStore())

    assert cfg.get("tools.serper_search.api_key") == ""


def test_config_logs_and_falls_back_to_empty_when_secret_lookup_fails(tmp_path, caplog):
    class BrokenStore:
        def is_available(self) -> bool:
            return True

        def get(self, ref: str) -> str | None:
            raise SecretStoreError(f"读取 secret 失败: {ref}")

    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "llm:\n"
        "  providers:\n"
        "    qwen:\n"
        "      api_key: ${secret:agentos/llm.providers.qwen.api_key}\n",
        encoding="utf-8",
    )

    cfg = Config(config_path=config_path, secret_store=BrokenStore())

    assert cfg.get("llm.providers.qwen.api_key") == ""
    assert "读取 secret 失败" in caplog.text
