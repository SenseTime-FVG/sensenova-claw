"""SecretStore 单测。"""

from __future__ import annotations

import pytest

from agentos.platform.secrets.store import InMemorySecretStore, KeyringSecretStore, SecretStoreError


def test_inmemory_secret_store_round_trip():
    store = InMemorySecretStore()

    store.set("agentos/tools.serper_search.api_key", "secret-1")

    assert store.get("agentos/tools.serper_search.api_key") == "secret-1"


def test_inmemory_secret_store_delete():
    store = InMemorySecretStore()
    ref = "agentos/llm.providers.openai.api_key"
    store.set(ref, "secret-2")

    store.delete(ref)

    assert store.get(ref) is None


def test_keyring_secret_store_wraps_backend_errors():
    class BrokenBackend:
        @staticmethod
        def get_password(service_name: str, username: str):
            raise RuntimeError("boom")

    store = KeyringSecretStore(service_name="agentos", backend=BrokenBackend())

    with pytest.raises(SecretStoreError, match="读取 secret 失败"):
        store.get("agentos/tools.serper_search.api_key")
