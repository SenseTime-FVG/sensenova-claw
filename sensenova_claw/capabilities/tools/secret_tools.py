from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sensenova_claw.capabilities.tools.base import Tool, ToolRiskLevel
from sensenova_claw.platform.secrets.store import (
    FileSecretStore,
    FallbackSecretStore,
    KeyringSecretStore,
)


class _BrokenSecretStore:
    def is_available(self) -> bool:
        return False

    def get(self, ref: str) -> str | None:
        raise RuntimeError(f"secret backend disabled: {ref}")

    def set(self, ref: str, value: str) -> None:
        raise RuntimeError(f"secret backend disabled: {ref}")

    def delete(self, ref: str) -> None:
        raise RuntimeError(f"secret backend disabled: {ref}")


def _secret_file() -> Path:
    return Path(
        os.environ.get(
            "SENSENOVA_SECRET_TOOLS_SECRET_FILE",
            str(Path.home() / ".sensenova-claw" / "data" / "secret" / "secret.yml"),
        )
    ).resolve()


def _build_secret_store() -> FallbackSecretStore:
    if os.environ.get("SENSENOVA_SECRET_TOOLS_DISABLE_KEYRING") == "1":
        return FallbackSecretStore(
            primary=_BrokenSecretStore(),
            fallback=FileSecretStore(secret_file=_secret_file()),
        )
    return FallbackSecretStore(
        primary=KeyringSecretStore(),
        fallback=FileSecretStore(secret_file=_secret_file()),
    )


def normalize_secret_path(path: str) -> str:
    normalized = path.strip()
    if normalized.startswith("secret:"):
        normalized = normalized[len("secret:"):]
    if not normalized:
        raise ValueError("path 不能为空")
    if not normalized.startswith(("tools.", "skills.", "plugins.")):
        raise ValueError(f"不支持的 secret path: {path}")
    return normalized


def secret_ref_from_path(path: str) -> str:
    return f"sensenova_claw/{normalize_secret_path(path)}"


class GetSecretTool(Tool):
    name = "get_secret"
    description = ("从 secret store 读取 skills/tools/plugins 的 secret。"
                   "每次调用skill/tool/plugin需要secret(如api_key,api_secret)时必须调用。"
                   "每次需要从环境变量/config文件获取skill/tool/plugin的secret(如api_key,api_secret) 时必须调用")
    risk_level = ToolRiskLevel.MEDIUM
    parameters = {
        "type": "object",
        "properties": {
            "path":
                {
                    "type": "string",
                    "description": "secret 路径，支持 secret: 前缀。\n"
                                   "- skill应填: skills.<skill_name>.<secret_name>\n"
                                   "- tool应填: tools.<tool_name>.<secret_name>\n"
                                   "- plugin应填: plugins.<plugin_name>.<secret_name>\n"
                },
        },
        "required": ["path"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        path = str(kwargs.get("path", "")).strip()
        normalized_path = normalize_secret_path(path)
        ref = secret_ref_from_path(normalized_path)
        store = _build_secret_store()
        value = store.get(ref) or ""
        return {
            "ok": True,
            "path": normalized_path,
            "ref": ref,
            "value": value,
        }


class WriteSecretTool(Tool):
    name = "write_secret"
    description = ("将 skills/tools/plugins 的 secret(如api_key,api_secret) 写入 secret store。"
                   "每次用户给出 skills/tools/plugins 的 secret必须调用。"
                   "如果是`get_secret` tool获取的secret不需要调用该工具写入。")
    risk_level = ToolRiskLevel.MEDIUM
    parameters = {
        "type": "object",
        "properties": {
            "path":
                {
                    "type": "string",
                    "description": "secret 路径，支持 secret: 前缀\n"
                                   "- skill应填: skills.<skill_name>.<secret_name>\n"
                                   "- tool应填: tools.<tool_name>.<secret_name>\n"
                                   "- plugin应填: plugins.<plugin_name>.<secret_name>\n"
                },
            "value": {"type": "string", "description": "要写入的 secret 明文"},
        },
        "required": ["path", "value"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        path = str(kwargs.get("path", "")).strip()
        value = kwargs.get("value")
        if not isinstance(value, str):
            raise ValueError("write_secret 要求 value 为字符串")
        normalized_path = normalize_secret_path(path)
        ref = secret_ref_from_path(normalized_path)
        store = _build_secret_store()
        store.set(ref, value)
        return {
            "ok": True,
            "path": normalized_path,
            "ref": ref,
        }
