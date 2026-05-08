from __future__ import annotations

import base64
import binascii
import json
import os
import subprocess
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterator, Protocol

from sensenova_claw.platform.config.workspace import default_sensenova_claw_home

OPENAI_CODEX_PROVIDER = "openai-codex"
OPENAI_CODEX_DEFAULT_PROFILE_ID = "openai-codex:default"
OAUTH_REFRESH_SKEW_MS = 5 * 60 * 1000


class OpenAICodexOAuthError(RuntimeError):
    """Raised when OpenAI Codex OAuth credentials cannot be resolved."""


class OAuthExecutorResult(Protocol):
    returncode: int
    stdout: str
    stderr: str


OAuthExecutor = Callable[[list[str]], OAuthExecutorResult]


@dataclass(frozen=True)
class OAuthCredential:
    provider: str
    access: str
    refresh: str
    expires: int
    email: str | None = None
    type: str = "oauth"
    display_name: str | None = None
    account_id: str | None = None
    id_token: str | None = None

    @classmethod
    def from_mapping(cls, value: dict) -> "OAuthCredential":
        provider = str(value.get("provider") or OPENAI_CODEX_PROVIDER)
        access = str(value.get("access") or "")
        refresh = str(value.get("refresh") or "")
        expires = int(value.get("expires") or 0)
        if not access or not refresh:
            raise OpenAICodexOAuthError("OAuth credential is missing access or refresh token")
        return cls(
            provider=provider,
            access=access,
            refresh=refresh,
            expires=expires,
            email=value.get("email") if isinstance(value.get("email"), str) else None,
            type=str(value.get("type") or "oauth"),
            display_name=value.get("displayName") if isinstance(value.get("displayName"), str) else None,
            account_id=value.get("accountId") if isinstance(value.get("accountId"), str) else None,
            id_token=value.get("idToken") if isinstance(value.get("idToken"), str) else None,
        )

    def to_store_dict(self) -> dict:
        data = asdict(self)
        data["displayName"] = data.pop("display_name")
        data["accountId"] = data.pop("account_id")
        data["idToken"] = data.pop("id_token")
        return {key: value for key, value in data.items() if value is not None}

    def is_usable(self, now_ms: int | None = None) -> bool:
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        return bool(self.access) and self.expires > now + OAUTH_REFRESH_SKEW_MS


class AuthProfileStore:
    def __init__(self, path: Path | None = None):
        self.path = (path or default_auth_profile_store_path()).expanduser().resolve()

    def load(self) -> dict:
        if not self.path.exists():
            return {"version": 1, "profiles": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise OpenAICodexOAuthError(f"Invalid auth profile store: {self.path}") from exc
        if not isinstance(data, dict):
            raise OpenAICodexOAuthError(f"Invalid auth profile store: {self.path}")
        profiles = data.get("profiles")
        if not isinstance(profiles, dict):
            data["profiles"] = {}
        data.setdefault("version", 1)
        return data

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def load_profile(self, profile_id: str = OPENAI_CODEX_DEFAULT_PROFILE_ID) -> OAuthCredential:
        profile = self.load().get("profiles", {}).get(profile_id)
        if not isinstance(profile, dict) or profile.get("type") != "oauth":
            raise OpenAICodexOAuthError(f"OAuth profile not found: {profile_id}")
        credential = OAuthCredential.from_mapping(profile)
        if credential.provider != OPENAI_CODEX_PROVIDER:
            raise OpenAICodexOAuthError(f"OAuth profile {profile_id} is not for {OPENAI_CODEX_PROVIDER}")
        return credential

    def save_profile(
        self,
        profile_id: str,
        credential: OAuthCredential,
        *,
        existing: dict | None = None,
    ) -> None:
        data = existing if existing is not None else self.load()
        profiles = data.setdefault("profiles", {})
        profiles[profile_id] = credential.to_store_dict()
        self.save(data)

    def delete_profile(
        self,
        profile_id: str = OPENAI_CODEX_DEFAULT_PROFILE_ID,
        *,
        existing: dict | None = None,
    ) -> None:
        data = existing if existing is not None else self.load()
        profiles = data.setdefault("profiles", {})
        if isinstance(profiles, dict):
            profiles.pop(profile_id, None)
        self.save(data)

    @contextmanager
    def locked(self) -> Iterator[None]:
        with _file_lock(self.path.with_suffix(self.path.suffix + ".lock")):
            yield


class OpenAICodexOAuth:
    def __init__(
        self,
        *,
        store: AuthProfileStore | None = None,
        profile_id: str = OPENAI_CODEX_DEFAULT_PROFILE_ID,
        executor: OAuthExecutor | None = None,
    ):
        self.store = store or AuthProfileStore()
        self.profile_id = profile_id
        self._executor = executor

    def resolve_access_token(self) -> str:
        with _file_lock(default_refresh_lock_path(self.profile_id)):
            with self.store.locked():
                data = self.store.load()
                credential = self.store.load_profile(self.profile_id)
                if credential.is_usable():
                    return credential.access
                refreshed = self._refresh(credential)
                self.store.save_profile(self.profile_id, refreshed, existing=data)
                return refreshed.access

    def login(self, *, is_remote: bool = False) -> OAuthCredential:
        args = ["login"]
        if is_remote:
            args.append("--remote")
        credential = self._parse_credential(self._execute(args, None))
        with self.store.locked():
            data = self.store.load()
            self.store.save_profile(self.profile_id, credential, existing=data)
        return credential

    def _refresh(self, credential: OAuthCredential) -> OAuthCredential:
        return self._parse_credential(self._execute(["refresh"], credential))

    def _execute(self, args: list[str], credential: OAuthCredential | None) -> OAuthExecutorResult:
        if self._executor is not None:
            result = self._executor(args)
        else:
            result = _run_node_sidecar(args, credential)
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "OpenAI Codex OAuth command failed").strip()
            raise OpenAICodexOAuthError(message)
        return result

    def _parse_credential(self, result: OAuthExecutorResult) -> OAuthCredential:
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise OpenAICodexOAuthError("OpenAI Codex OAuth command returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise OpenAICodexOAuthError("OpenAI Codex OAuth command returned invalid credential")
        credential = OAuthCredential.from_mapping(payload)
        if credential.provider != OPENAI_CODEX_PROVIDER:
            raise OpenAICodexOAuthError(f"Unexpected OAuth provider: {credential.provider}")
        return credential


def default_auth_profile_store_path() -> Path:
    return default_sensenova_claw_home() / "data" / "auth-profiles.json"


def default_codex_cli_auth_path() -> Path:
    return default_sensenova_claw_home() / "data" / "openai-codex" / "auth.json"


def default_refresh_lock_path(profile_id: str) -> Path:
    safe_profile = profile_id.replace("/", "_").replace("\\", "_").replace(":", "_")
    return default_sensenova_claw_home() / "data" / "oauth-refresh" / f"{safe_profile}.lock"


def resolve_openai_codex_access_token() -> str:
    return OpenAICodexOAuth().resolve_access_token()


def login_openai_codex_oauth(*, is_remote: bool = False) -> OAuthCredential:
    return OpenAICodexOAuth().login(is_remote=is_remote)


def relogin_openai_codex_oauth(
    *,
    is_remote: bool = False,
    store: AuthProfileStore | None = None,
    executor: OAuthExecutor | None = None,
) -> OAuthCredential:
    target_store = store or AuthProfileStore()
    with target_store.locked():
        data = target_store.load()
        target_store.delete_profile(existing=data)
    _delete_default_codex_cli_auth_copy()
    return OpenAICodexOAuth(store=target_store, executor=executor).login(is_remote=is_remote)


def import_codex_cli_auth(
    *,
    store: AuthProfileStore | None = None,
    auth_path: Path | None = None,
) -> OAuthCredential:
    auth_file = (auth_path or default_codex_cli_auth_path()).expanduser()
    if not auth_file.exists():
        raise OpenAICodexOAuthError(
            "未找到本地 Codex OAuth 凭据。请先在终端运行 sensenova-claw auth openai-codex login，"
            "或使用 Codex CLI 完成登录。"
        )
    credential = _credential_from_codex_cli_auth_file(auth_file)
    target_store = store or AuthProfileStore()
    with target_store.locked():
        data = target_store.load()
        target_store.save_profile(OPENAI_CODEX_DEFAULT_PROFILE_ID, credential, existing=data)
    return credential


def get_openai_codex_oauth_status() -> dict[str, str | int | bool | None]:
    try:
        credential = AuthProfileStore().load_profile()
    except OpenAICodexOAuthError:
        return {"logged_in": False, "email": None, "expires": None}
    return {
        "logged_in": True,
        "email": credential.email,
        "expires": credential.expires,
    }


def _run_node_sidecar(args: list[str], credential: OAuthCredential | None) -> subprocess.CompletedProcess[str]:
    script = Path(__file__).resolve().parents[3] / "scripts" / "openai_codex_oauth.mjs"
    input_data = json.dumps(credential.to_store_dict()) if credential else None
    return subprocess.run(
        ["node", str(script), *args],
        input=input_data,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _decode_jwt_payload(token: str) -> dict:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8")
        value = json.loads(decoded)
    except (UnicodeDecodeError, ValueError, binascii.Error):
        return {}
    return value if isinstance(value, dict) else {}


def _credential_from_codex_cli_auth_file(auth_file: Path) -> OAuthCredential:
    try:
        payload = json.loads(auth_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OpenAICodexOAuthError(f"无法读取本地 Codex OAuth 凭据: {auth_file}") from exc
    if not isinstance(payload, dict):
        raise OpenAICodexOAuthError(f"本地 Codex OAuth 凭据格式无效: {auth_file}")
    tokens = payload.get("tokens")
    if not isinstance(tokens, dict):
        raise OpenAICodexOAuthError(f"本地 Codex OAuth 凭据缺少 tokens: {auth_file}")
    access = tokens.get("access_token")
    refresh = tokens.get("refresh_token")
    if not isinstance(access, str) or not access:
        raise OpenAICodexOAuthError(f"本地 Codex OAuth 凭据缺少 access_token: {auth_file}")
    if not isinstance(refresh, str) or not refresh:
        raise OpenAICodexOAuthError(f"本地 Codex OAuth 凭据缺少 refresh_token: {auth_file}")
    id_token = tokens.get("id_token") if isinstance(tokens.get("id_token"), str) else None
    id_payload = _decode_jwt_payload(id_token) if id_token else {}
    access_payload = _decode_jwt_payload(access)
    return OAuthCredential(
        provider=OPENAI_CODEX_PROVIDER,
        access=access,
        refresh=refresh,
        expires=_resolve_codex_cli_expires_ms(payload, access_payload, id_payload, auth_file),
        email=_extract_email(id_payload),
        account_id=_extract_account_id(tokens, id_payload),
        id_token=id_token,
    )


def _resolve_codex_cli_expires_ms(
    payload: dict,
    access_payload: dict,
    id_payload: dict,
    auth_file: Path,
) -> int:
    raw_expires = payload.get("expires")
    if raw_expires is not None:
        try:
            expires_ms = int(raw_expires)
        except (TypeError, ValueError) as exc:
            raise OpenAICodexOAuthError(f"本地 Codex OAuth 凭据缺少有效 expires: {auth_file}") from exc
        if expires_ms > 0:
            return expires_ms
    for token_payload in (access_payload, id_payload):
        exp = token_payload.get("exp")
        if isinstance(exp, (int, float)) and exp > 0:
            return int(exp * 1000)
    raise OpenAICodexOAuthError(f"本地 Codex OAuth 凭据缺少有效 expires: {auth_file}")


def _delete_default_codex_cli_auth_copy() -> None:
    try:
        default_codex_cli_auth_path().unlink(missing_ok=True)
    except OSError:
        pass


def _extract_email(payload: dict) -> str | None:
    email = payload.get("email")
    if isinstance(email, str) and email:
        return email
    profile = payload.get("https://api.openai.com/profile")
    if isinstance(profile, dict):
        email = profile.get("email")
        if isinstance(email, str) and email:
            return email
    return None


def _extract_account_id(tokens: dict, payload: dict) -> str | None:
    account_id = tokens.get("account_id")
    if isinstance(account_id, str) and account_id:
        return account_id
    auth = payload.get("https://api.openai.com/auth")
    if isinstance(auth, dict):
        account_id = auth.get("chatgpt_account_id")
        if isinstance(account_id, str) and account_id:
            return account_id
    return None


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        if os.name == "nt":
            yield
            return
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
