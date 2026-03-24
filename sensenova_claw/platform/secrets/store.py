"""SecretStore 抽象与基础实现。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class SecretStoreError(RuntimeError):
    """SecretStore 统一错误类型。"""


class InMemorySecretStore:
    """测试用内存 secret store。"""

    def __init__(self):
        self._values: dict[str, str] = {}

    def is_available(self) -> bool:
        return True

    def get(self, ref: str) -> str | None:
        return self._values.get(ref)

    def set(self, ref: str, value: str) -> None:
        self._values[ref] = value

    def delete(self, ref: str) -> None:
        self._values.pop(ref, None)


class KeyringSecretStore:
    """基于 python-keyring 的 secret store。"""

    def __init__(self, service_name: str = "sensenova_claw", backend: Any | None = None):
        self._service_name = service_name
        self._backend = backend

    def _keyring(self) -> Any:
        if self._backend is not None:
            return self._backend
        try:
            import keyring
        except Exception as exc:  # pragma: no cover - 真实依赖在集成环境验证
            raise SecretStoreError("keyring 不可用") from exc
        return keyring

    def is_available(self) -> bool:
        try:
            self._keyring()
        except SecretStoreError:
            return False
        return True

    def get(self, ref: str) -> str | None:
        try:
            return self._keyring().get_password(self._service_name, ref)
        except Exception as exc:
            raise SecretStoreError(f"读取 secret 失败: {ref}") from exc

    def set(self, ref: str, value: str) -> None:
        try:
            self._keyring().set_password(self._service_name, ref, value)
        except Exception as exc:
            raise SecretStoreError(f"写入 secret 失败: {ref}") from exc

    def delete(self, ref: str) -> None:
        try:
            self._keyring().delete_password(self._service_name, ref)
        except Exception as exc:
            raise SecretStoreError(f"删除 secret 失败: {ref}") from exc


class FileSecretStore:
    """基于本地 secret.yml 的回退 secret store。"""

    def __init__(self, secret_file: Path | str | None = None):
        self._secret_file = Path(secret_file or default_secret_file_path()).expanduser().resolve()

    def is_available(self) -> bool:
        return True

    def get(self, ref: str) -> str | None:
        data = self._load()
        value = data.get(ref)
        return value if isinstance(value, str) else None

    def set(self, ref: str, value: str) -> None:
        data = self._load()
        data[ref] = value
        self._write(data)

    def delete(self, ref: str) -> None:
        data = self._load()
        if ref in data:
            data.pop(ref, None)
            self._write(data)

    def _load(self) -> dict[str, str]:
        if not self._secret_file.exists():
            return {}
        raw = yaml.safe_load(self._secret_file.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            return {}
        return {str(key): value for key, value in raw.items() if isinstance(value, str)}

    def _write(self, data: dict[str, str]) -> None:
        self._secret_file.parent.mkdir(parents=True, exist_ok=True)
        self._secret_file.write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=True),
            encoding="utf-8",
        )


class FallbackSecretStore:
    """优先 keyring，失败时回退到本地文件的组合 secret store。"""

    def __init__(self, primary: Any, fallback: Any):
        self._primary = primary
        self._fallback = fallback

    def is_available(self) -> bool:
        primary_available = getattr(self._primary, "is_available", lambda: True)()
        fallback_available = getattr(self._fallback, "is_available", lambda: True)()
        return bool(primary_available or fallback_available)

    def get(self, ref: str) -> str | None:
        try:
            value = self._primary.get(ref)
        except Exception:
            value = None
        if isinstance(value, str) and value:
            return value
        return self._fallback.get(ref)

    def set(self, ref: str, value: str) -> None:
        try:
            self._primary.set(ref, value)
        except Exception:
            self._fallback.set(ref, value)
            return
        try:
            self._fallback.delete(ref)
        except Exception:
            pass

    def delete(self, ref: str) -> None:
        primary_error: Exception | None = None
        try:
            self._primary.delete(ref)
        except Exception as exc:
            primary_error = exc

        try:
            self._fallback.delete(ref)
        except Exception as exc:
            if primary_error is not None:
                raise SecretStoreError(f"删除 secret 失败: {ref}") from exc


def default_secret_file_path() -> Path:
    return (Path.home() / ".sensenova-claw" / "data" / "secret" / "secret.yml").expanduser().resolve()


def build_default_secret_store() -> FallbackSecretStore:
    return FallbackSecretStore(
        primary=KeyringSecretStore(),
        fallback=FileSecretStore(),
    )


def describe_secret_store_status(store: Any) -> tuple[bool, str]:
    """返回当前 secret store 的 keyring 可用性与启动提示文案。"""
    primary = getattr(store, "_primary", None)
    fallback = getattr(store, "_fallback", None)

    if primary is not None and fallback is not None:
        keyring_available = _probe_secret_store(primary)
        fallback_path = getattr(fallback, "_secret_file", default_secret_file_path())
        if keyring_available:
            return True, "Secret store ready: keyring available"
        return False, f"Secret store ready: keyring unavailable, fallback file={fallback_path}"

    available = _probe_secret_store(store)
    if available:
        return True, "Secret store ready"
    return False, "Secret store unavailable"


def _probe_secret_store(store: Any) -> bool:
    """探测 store 是否可实际完成一次读取，而不只是不报 import 错。"""
    is_available = getattr(store, "is_available", lambda: False)
    try:
        if not is_available():
            return False
        get = getattr(store, "get", None)
        if callable(get):
            get("__sensenova_claw_probe__")
        return True
    except Exception:
        return False
