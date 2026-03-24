"""SecretStore 单测。"""

from __future__ import annotations

import yaml
import pytest

from sensenova_claw.platform.secrets.store import (
    FileSecretStore,
    FallbackSecretStore,
    InMemorySecretStore,
    KeyringSecretStore,
    SecretStoreError,
)


def test_inmemory_secret_store_round_trip():
    store = InMemorySecretStore()

    store.set("sensenova_claw/tools.serper_search.api_key", "secret-1")

    assert store.get("sensenova_claw/tools.serper_search.api_key") == "secret-1"


def test_inmemory_secret_store_delete():
    store = InMemorySecretStore()
    ref = "sensenova_claw/llm.providers.openai.api_key"
    store.set(ref, "secret-2")

    store.delete(ref)

    assert store.get(ref) is None


def test_keyring_secret_store_wraps_backend_errors():
    class BrokenBackend:
        @staticmethod
        def get_password(service_name: str, username: str):
            raise RuntimeError("boom")

    store = KeyringSecretStore(service_name="sensenova_claw", backend=BrokenBackend())

    with pytest.raises(SecretStoreError, match="读取 secret 失败"):
        store.get("sensenova_claw/tools.serper_search.api_key")


def test_file_secret_store_round_trip(tmp_path):
    secret_file = tmp_path / "data" / "secret" / "secret.yml"
    store = FileSecretStore(secret_file=secret_file)

    store.set("sensenova_claw/tools.serper_search.api_key", "secret-3")

    assert store.get("sensenova_claw/tools.serper_search.api_key") == "secret-3"
    written = yaml.safe_load(secret_file.read_text(encoding="utf-8"))
    assert written == {"sensenova_claw/tools.serper_search.api_key": "secret-3"}


def test_fallback_secret_store_writes_file_when_keyring_set_fails(tmp_path):
    class BrokenBackend:
        @staticmethod
        def set_password(service_name: str, username: str, password: str):
            raise RuntimeError("boom")

    secret_file = tmp_path / "data" / "secret" / "secret.yml"
    primary = KeyringSecretStore(service_name="sensenova_claw", backend=BrokenBackend())
    fallback = FileSecretStore(secret_file=secret_file)
    store = FallbackSecretStore(primary=primary, fallback=fallback)

    store.set("sensenova_claw/llm.providers.openai.api_key", "sk-file-fallback")

    assert fallback.get("sensenova_claw/llm.providers.openai.api_key") == "sk-file-fallback"


def test_fallback_secret_store_reads_file_when_keyring_get_fails(tmp_path):
    class BrokenBackend:
        @staticmethod
        def get_password(service_name: str, username: str):
            raise RuntimeError("boom")

    secret_file = tmp_path / "data" / "secret" / "secret.yml"
    fallback = FileSecretStore(secret_file=secret_file)
    fallback.set("sensenova_claw/tools.tavily_search.api_key", "tvly-file-fallback")
    primary = KeyringSecretStore(service_name="sensenova_claw", backend=BrokenBackend())
    store = FallbackSecretStore(primary=primary, fallback=fallback)

    assert store.get("sensenova_claw/tools.tavily_search.api_key") == "tvly-file-fallback"


def test_fallback_secret_store_deletes_file_when_keyring_delete_fails(tmp_path):
    class BrokenBackend:
        @staticmethod
        def delete_password(service_name: str, username: str):
            raise RuntimeError("boom")

    secret_file = tmp_path / "data" / "secret" / "secret.yml"
    fallback = FileSecretStore(secret_file=secret_file)
    fallback.set("sensenova_claw/tools.brave_search.api_key", "brave-file-fallback")
    primary = KeyringSecretStore(service_name="sensenova_claw", backend=BrokenBackend())
    store = FallbackSecretStore(primary=primary, fallback=fallback)

    store.delete("sensenova_claw/tools.brave_search.api_key")

    assert fallback.get("sensenova_claw/tools.brave_search.api_key") is None
