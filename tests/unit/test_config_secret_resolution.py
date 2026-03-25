"""Config 的 secret 解析单测。"""

from __future__ import annotations

import pytest

from sensenova_claw.platform.config.config import Config
from sensenova_claw.platform.secrets.store import (
    FileSecretStore,
    FallbackSecretStore,
    InMemorySecretStore,
    KeyringSecretStore,
    SecretStoreError,
)


def test_config_resolves_secret_reference(tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "llm:\n"
        "  providers:\n"
        "    openai:\n"
        "      api_key: ${secret:sensenova_claw/llm.providers.openai.api_key}\n",
        encoding="utf-8",
    )
    store = InMemorySecretStore()
    store.set("sensenova_claw/llm.providers.openai.api_key", "sk-from-secret-store")

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
        "    api_key: ${secret:sensenova_claw/tools.serper_search.api_key}\n",
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
        "      api_key: ${secret:sensenova_claw/llm.providers.qwen.api_key}\n",
        encoding="utf-8",
    )

    cfg = Config(config_path=config_path, secret_store=BrokenStore())

    assert cfg.get("llm.providers.qwen.api_key") == ""
    assert "读取 secret 失败" in caplog.text


def test_config_resolves_secret_reference_from_file_fallback_when_keyring_get_fails(tmp_path):
    class BrokenBackend:
        @staticmethod
        def get_password(service_name: str, username: str):
            raise RuntimeError("boom")

    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "llm:\n"
        "  providers:\n"
        "    openai:\n"
        "      api_key: ${secret:sensenova_claw/llm.providers.openai.api_key}\n",
        encoding="utf-8",
    )
    file_store = FileSecretStore(secret_file=tmp_path / ".sensenova-claw" / "data" / "secret" / "secret.yml")
    file_store.set("sensenova_claw/llm.providers.openai.api_key", "sk-from-file-fallback")
    store = FallbackSecretStore(
        primary=KeyringSecretStore(service_name="sensenova_claw", backend=BrokenBackend()),
        fallback=file_store,
    )

    cfg = Config(config_path=config_path, secret_store=store)

    assert cfg.get("llm.providers.openai.api_key") == "sk-from-file-fallback"
