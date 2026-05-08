from __future__ import annotations

import json
import base64
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from sensenova_claw.platform.auth.openai_codex_oauth import (
    AuthProfileStore,
    OAuthCredential,
    OpenAICodexOAuth,
    OpenAICodexOAuthError,
    import_codex_cli_auth,
    relogin_openai_codex_oauth,
)


def _unsigned_jwt(payload: dict) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii").rstrip("=")
    return f"header.{encoded}.signature"


def test_resolve_access_token_returns_cached_token_when_not_near_expiry(tmp_path: Path) -> None:
    store_path = tmp_path / "auth-profiles.json"
    store = AuthProfileStore(store_path)
    store.save_profile(
        "openai-codex:default",
        OAuthCredential(
            provider="openai-codex",
            access="cached-access",
            refresh="cached-refresh",
            expires=int(time.time() * 1000) + 30 * 60 * 1000,
            email="user@example.com",
        ),
    )
    oauth = OpenAICodexOAuth(store=store, executor=lambda *_args: pytest.fail("unexpected refresh"))

    token = oauth.resolve_access_token()

    assert token == "cached-access"


def test_resolve_access_token_refreshes_expired_token_under_store_lock(tmp_path: Path) -> None:
    store_path = tmp_path / "auth-profiles.json"
    store = AuthProfileStore(store_path)
    store.save_profile(
        "openai-codex:default",
        OAuthCredential(
            provider="openai-codex",
            access="expired-access",
            refresh="refresh-token",
            expires=int(time.time() * 1000) - 1000,
            email="user@example.com",
        ),
    )
    calls: list[list[str]] = []

    def fake_executor(args: list[str]) -> SimpleNamespace:
        calls.append(args)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "access": "fresh-access",
                    "refresh": "fresh-refresh",
                    "expires": int(time.time() * 1000) + 60 * 60 * 1000,
                    "provider": "openai-codex",
                    "email": "user@example.com",
                }
            ),
            stderr="",
        )

    oauth = OpenAICodexOAuth(store=store, executor=fake_executor)

    token = oauth.resolve_access_token()

    assert token == "fresh-access"
    assert calls == [["refresh"]]
    assert store.load_profile("openai-codex:default").access == "fresh-access"


def test_resolve_access_token_wraps_refresh_failures(tmp_path: Path) -> None:
    store = AuthProfileStore(tmp_path / "auth-profiles.json")
    store.save_profile(
        "openai-codex:default",
        OAuthCredential(
            provider="openai-codex",
            access="expired-access",
            refresh="refresh-token",
            expires=int(time.time() * 1000) - 1000,
        ),
    )

    def fake_executor(_args: list[str]) -> SimpleNamespace:
        return SimpleNamespace(returncode=1, stdout="", stderr="refresh failed")

    oauth = OpenAICodexOAuth(store=store, executor=fake_executor)

    with pytest.raises(OpenAICodexOAuthError, match="refresh failed"):
        oauth.resolve_access_token()


def test_login_persists_openai_codex_default_profile(tmp_path: Path) -> None:
    store = AuthProfileStore(tmp_path / "auth-profiles.json")

    def fake_executor(args: list[str]) -> SimpleNamespace:
        assert args == ["login", "--remote"]
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "access": "login-access",
                    "refresh": "login-refresh",
                    "expires": int(time.time() * 1000) + 60 * 60 * 1000,
                    "provider": "openai-codex",
                    "email": "user@example.com",
                }
            ),
            stderr="",
        )

    oauth = OpenAICodexOAuth(store=store, executor=fake_executor)

    credential = oauth.login(is_remote=True)

    assert credential.access == "login-access"
    assert store.load_profile("openai-codex:default").refresh == "login-refresh"


def test_relogin_clears_existing_profile_before_browser_login(tmp_path: Path) -> None:
    store = AuthProfileStore(tmp_path / "auth-profiles.json")
    store.save_profile(
        "openai-codex:default",
        OAuthCredential(
            provider="openai-codex",
            access="old-access",
            refresh="old-refresh",
            expires=1893456000000,
        ),
    )
    observed: list[str] = []

    def fake_executor(args: list[str]) -> SimpleNamespace:
        observed.append(store.load().get("profiles", {}).get("openai-codex:default", {}).get("access", "missing"))
        assert args == ["login"]
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({
                "access": "new-access",
                "refresh": "new-refresh",
                "expires": 1893457000000,
                "provider": "openai-codex",
                "email": "user@example.com",
            }),
            stderr="",
        )

    credential = relogin_openai_codex_oauth(store=store, executor=fake_executor)

    assert observed == ["missing"]
    assert credential.access == "new-access"
    assert store.load_profile("openai-codex:default").refresh == "new-refresh"


def test_import_codex_cli_auth_persists_existing_codex_tokens(tmp_path: Path) -> None:
    store = AuthProfileStore(tmp_path / "auth-profiles.json")
    codex_auth_path = tmp_path / "openai-codex" / "auth.json"
    codex_auth_path.parent.mkdir()
    codex_auth_path.write_text(
        json.dumps({
            "tokens": {
                "access_token": "cli-access",
                "refresh_token": "cli-refresh",
                "id_token": _unsigned_jwt({"email": "cli@example.com"}),
                "account_id": "account-1",
            },
            "expires": 1893456000000,
        }),
        encoding="utf-8",
    )

    credential = import_codex_cli_auth(store=store, auth_path=codex_auth_path)

    assert credential.access == "cli-access"
    assert credential.refresh == "cli-refresh"
    assert credential.email == "cli@example.com"
    assert store.load_profile("openai-codex:default").access == "cli-access"


def test_import_codex_cli_auth_derives_expires_from_access_token(tmp_path: Path) -> None:
    store = AuthProfileStore(tmp_path / "auth-profiles.json")
    codex_auth_path = tmp_path / ".codex" / "auth.json"
    codex_auth_path.parent.mkdir()
    codex_auth_path.write_text(
        json.dumps({
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": _unsigned_jwt({"exp": 1893456000}),
                "refresh_token": "cli-refresh",
            },
        }),
        encoding="utf-8",
    )

    credential = import_codex_cli_auth(store=store, auth_path=codex_auth_path)

    assert credential.expires == 1893456000000
    assert store.load_profile("openai-codex:default").expires == 1893456000000

