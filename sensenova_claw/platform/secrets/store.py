"""SecretStore 抽象与基础实现。"""

from __future__ import annotations

from typing import Any


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
