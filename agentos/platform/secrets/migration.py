"""明文 secret 迁移工具。"""

from __future__ import annotations

from typing import Any

from agentos.interfaces.http.config_store import (
    load_raw_config,
    reload_config,
    set_nested_value,
    write_raw_config,
)
from agentos.platform.config.config import Config
from agentos.platform.secrets.refs import build_secret_ref, is_secret_ref
from agentos.platform.secrets.registry import is_secret_path


def migrate_plaintext_secrets(cfg: Config, *, secret_store: Any) -> dict[str, Any]:
    """将 config.yml 中的明文敏感字段迁移到 secret store。"""
    setattr(cfg, "_secret_store", secret_store)
    raw_config = load_raw_config(cfg)
    migrated_paths: list[str] = []

    for path, value in _iter_leaf_values(raw_config):
        if not is_secret_path(path):
            continue
        if not isinstance(value, str) or not value:
            continue
        if is_secret_ref(value):
            continue
        if value.startswith("${") and value.endswith("}"):
            continue

        ref = f"agentos/{path}"
        secret_store.set(ref, value)
        set_nested_value(raw_config, path, build_secret_ref(ref))
        migrated_paths.append(path)

    if migrated_paths:
        write_raw_config(cfg, raw_config)
        reload_config(cfg)

    return {
        "migrated": len(migrated_paths),
        "migrated_paths": migrated_paths,
    }


def _iter_leaf_values(data: Any, prefix: str = "") -> list[tuple[str, Any]]:
    if isinstance(data, dict):
        result: list[tuple[str, Any]] = []
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else key
            result.extend(_iter_leaf_values(value, path))
        return result
    return [(prefix, data)]
