"""明文 secret 迁移工具。"""

from __future__ import annotations

from typing import Any

import yaml

from agentos.platform.config.config import Config
from agentos.platform.secrets.refs import build_secret_ref, is_secret_ref
from agentos.platform.secrets.registry import is_secret_path


def migrate_plaintext_secrets(cfg: Config, *, secret_store: Any) -> dict[str, Any]:
    """将 config.yml 中的明文敏感字段迁移到 secret store。"""
    setattr(cfg, "_secret_store", secret_store)
    raw_config = _load_raw_config(cfg)
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
        _set_nested_value(raw_config, path, build_secret_ref(ref))
        migrated_paths.append(path)

    if migrated_paths:
        _write_raw_config(cfg, raw_config)
        _reload_config(cfg)

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


def _load_raw_config(cfg: Config) -> dict[str, Any]:
    config_path = getattr(cfg, "_config_path", None)
    if not config_path or not config_path.exists():
        return {}
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return raw if isinstance(raw, dict) else {}


def _write_raw_config(cfg: Config, raw_config: dict[str, Any]) -> None:
    config_path = getattr(cfg, "_config_path", None)
    if config_path is None:
        raise RuntimeError("当前配置实例不支持直接写回 config.yml")
    config_path.write_text(
        yaml.dump(raw_config, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _reload_config(cfg: Config) -> None:
    cfg.data = cfg._load_config()


def _set_nested_value(target: dict[str, Any], dotted_path: str, value: Any) -> None:
    keys = dotted_path.split(".")
    current = target
    for key in keys[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    current[keys[-1]] = value
