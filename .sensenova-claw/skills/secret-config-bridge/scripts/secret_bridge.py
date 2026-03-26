from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml

from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.platform.config.config import Config
from sensenova_claw.platform.config.config_manager import ConfigManager
from sensenova_claw.platform.secrets.registry import is_secret_path
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


def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _config_path() -> Path:
    return Path(
        os.environ.get(
            "SENSENOVA_CLAW_SECRET_BRIDGE_CONFIG_PATH",
            str(_project_root() / "config.yml"),
        )
    ).resolve()


def _skills_dir() -> Path:
    return Path(
        os.environ.get(
            "SENSENOVA_CLAW_SECRET_BRIDGE_SKILLS_DIR",
            str(_project_root() / ".sensenova-claw" / "skills"),
        )
    ).resolve()


def _secret_file() -> Path:
    return Path(
        os.environ.get(
            "SENSENOVA_CLAW_SECRET_BRIDGE_SECRET_FILE",
            str(Path.home() / ".sensenova-claw" / "data" / "secret" / "secret.yml"),
        )
    ).resolve()


def _build_secret_store() -> FallbackSecretStore:
    if os.environ.get("SENSENOVA_CLAW_SECRET_BRIDGE_DISABLE_KEYRING") == "1":
        return FallbackSecretStore(
            primary=_BrokenSecretStore(),
            fallback=FileSecretStore(secret_file=_secret_file()),
        )
    return FallbackSecretStore(
        primary=KeyringSecretStore(),
        fallback=FileSecretStore(secret_file=_secret_file()),
    )


def _load_skill_secret_mapping(skill_name: str) -> dict[str, str]:
    secret_yml = _skills_dir() / skill_name / "secret.yml"
    if not secret_yml.exists():
        return {}
    raw = yaml.safe_load(secret_yml.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return {}
    return {str(key): value for key, value in raw.items() if isinstance(value, str)}


def _write_skill_secret_mapping(skill_name: str, env_name: str, secret_ref: str) -> None:
    skill_dir = _skills_dir() / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    secret_yml = skill_dir / "secret.yml"
    mapping = _load_skill_secret_mapping(skill_name)
    mapping[env_name] = secret_ref
    secret_yml.write_text(
        yaml.dump(mapping, default_flow_style=False, allow_unicode=True, sort_keys=True),
        encoding="utf-8",
    )


def _parse_secret_ref(secret_ref: str) -> tuple[str, str]:
    parts = secret_ref.split(":", 2)
    if len(parts) != 3 or parts[0] != "secret" or not parts[1] or not parts[2]:
        raise ValueError(f"非法 secret 引用: {secret_ref}")
    return parts[1], parts[2]


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flattened.update(_flatten(value, path))
        else:
            flattened[path] = value
    return flattened


async def _write_config(payload: dict[str, Any], *, secret_store: Any) -> dict[str, Any]:
    meta = payload.pop("__meta__", {})
    if not isinstance(meta, dict):
        raise ValueError("__meta__ 必须是对象")

    skill_name = str(meta.get("skill", "")).strip()
    env_name = str(meta.get("env", "")).strip()
    if not skill_name or not env_name:
        raise ValueError("write 模式要求 json.__meta__.skill 和 json.__meta__.env")

    flat = _flatten(payload)
    sensitive_paths = [
        path
        for path, value in flat.items()
        if is_secret_path(path) and isinstance(value, str) and value
    ]
    if len(sensitive_paths) != 1:
        raise ValueError("write 模式要求 payload 中恰好包含一个非空敏感路径")

    sensitive_path = sensitive_paths[0]
    sensitive_value = str(flat[sensitive_path])

    cfg = Config(config_path=_config_path(), secret_store=secret_store)
    manager = ConfigManager(
        config=cfg,
        event_bus=PublicEventBus(),
        secret_store=secret_store,
    )

    for section, section_data in payload.items():
        if isinstance(section_data, dict):
            await manager.update(section, section_data)

    secret_ref = f"secret:{skill_name}:{env_name}"
    secret_store.set(secret_ref, sensitive_value)
    _write_skill_secret_mapping(skill_name, env_name, secret_ref)

    return {
        "ok": True,
        "path": sensitive_path,
        "secret_ref": secret_ref,
    }


def _read_value(path: str, *, secret_store: Any) -> dict[str, Any]:
    if path.startswith("secret:"):
        skill_name, env_name = _parse_secret_ref(path)
        mapping = _load_skill_secret_mapping(skill_name)
        mapped_ref = mapping.get(env_name, path)
        value = secret_store.get(mapped_ref) or ""
        return {
            "ok": True,
            "path": path,
            "value": value,
            "source": "skill_secret_mapping",
        }

    cfg = Config(config_path=_config_path(), secret_store=secret_store)
    value = cfg.get(path, "") or ""
    return {
        "ok": True,
        "path": path,
        "value": value,
        "source": "config_path",
    }


def main() -> int:
    try:
        raw = sys.stdin.read().strip()
        if not raw:
            raise ValueError("缺少输入 JSON")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("输入必须是 JSON 对象")

        action = str(payload.get("action", "")).strip().lower()
        secret_store = _build_secret_store()

        if action == "read":
            path = str(payload.get("path", "")).strip()
            if not path:
                raise ValueError("read 模式要求提供 path")
            result = _read_value(path, secret_store=secret_store)
        elif action == "write":
            body = payload.get("json")
            if not isinstance(body, dict):
                raise ValueError("write 模式要求提供 json 对象")
            result = asyncio.run(_write_config(dict(body), secret_store=secret_store))
        else:
            raise ValueError(f"不支持的 action: {action}")

        sys.stdout.write(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        sys.stdout.write(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc).strip() or type(exc).__name__,
                },
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
