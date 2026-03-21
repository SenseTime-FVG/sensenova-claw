"""配置文件持久化辅助函数。

为多个 HTTP API 提供统一的 config.yml 读写与热重载逻辑。
"""

from __future__ import annotations

import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from agentos.platform.config.config import Config
from agentos.platform.secrets.refs import build_secret_ref, is_secret_ref
from agentos.platform.secrets.registry import is_secret_path

logger = logging.getLogger(__name__)


def get_config_path(cfg: Config) -> Path:
    """返回可写配置文件路径。"""
    path = getattr(cfg, "_config_path", None)
    if not isinstance(path, Path):
        raise RuntimeError("当前配置实例不支持直接写回 config.yml")
    return path


def load_raw_config(cfg: Config) -> dict[str, Any]:
    """读取原始 config.yml，保持未知 section 不丢失。"""
    config_path = get_config_path(cfg)
    if not config_path.exists():
        return {}

    raw = config_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    return data if isinstance(data, dict) else {}


def write_raw_config(cfg: Config, raw_config: dict[str, Any]) -> None:
    """写回 config.yml。"""
    config_path = get_config_path(cfg)
    yaml_text = yaml.dump(
        raw_config,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    config_path.write_text(yaml_text, encoding="utf-8")


def reload_config(cfg: Config) -> dict[str, Any]:
    """热重载配置对象。"""
    if getattr(cfg, "_config_path", None) is not None:
        cfg.data = cfg._load_config()
    else:
        cfg.data = cfg._load_config_from_project_root()
    return deepcopy(cfg.data)


def set_nested_value(target: dict[str, Any], dotted_path: str, value: Any) -> None:
    """按 a.b.c 形式写入嵌套字段。"""
    keys = dotted_path.split(".")
    current = target
    for key in keys[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    current[keys[-1]] = value


def get_nested_value(target: dict[str, Any], dotted_path: str, default: Any = None) -> Any:
    """按 a.b.c 形式读取嵌套字段。"""
    current: Any = target
    for key in dotted_path.split("."):
        if not isinstance(current, dict):
            return default
        if key not in current:
            return default
        current = current[key]
    return current


def persist_section_updates(cfg: Config, updates: dict[str, Any]) -> dict[str, Any]:
    """按顶层 section 写入配置并热重载。"""
    raw_config = load_raw_config(cfg)
    for section, value in updates.items():
        raw_config[section] = value
    write_raw_config(cfg, raw_config)
    return reload_config(cfg)


def persist_path_updates(
    cfg: Config,
    updates: dict[str, Any],
    *,
    secret_store: Any | None = None,
) -> dict[str, Any]:
    """按 dotted path 写入配置并热重载。"""
    if secret_store is not None:
        setattr(cfg, "_secret_store", secret_store)
    raw_config = load_raw_config(cfg)
    for path, value in updates.items():
        if is_secret_path(path) and secret_store is not None:
            ref = f"agentos/{path}"
            if value:
                try:
                    secret_store.set(ref, value)
                    set_nested_value(raw_config, path, build_secret_ref(ref))
                except Exception:
                    # keyring 不可用时降级为明文写入
                    logger.warning("secret store 不可用，%s 将明文写入 config.yml", path)
                    set_nested_value(raw_config, path, value)
            else:
                try:
                    existing_raw = get_nested_value(raw_config, path)
                    if isinstance(existing_raw, str) and is_secret_ref(existing_raw):
                        secret_store.delete(ref)
                except Exception:
                    logger.warning("secret store 不可用，跳过删除 %s", path)
                set_nested_value(raw_config, path, "")
        else:
            set_nested_value(raw_config, path, value)
    write_raw_config(cfg, raw_config)
    return reload_config(cfg)
