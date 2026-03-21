"""ConfigManager — 配置管理器：统一入口，负责持久化、内存同步、事件通知。

合并了原 interfaces/http/config_store.py 的逻辑。
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from agentos.kernel.events.bus import PublicEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import CONFIG_UPDATED, SYSTEM_SESSION_ID
from agentos.platform.config.config import Config
from agentos.platform.secrets.refs import build_secret_ref, is_secret_ref
from agentos.platform.secrets.registry import is_secret_path

logger = logging.getLogger(__name__)


class ConfigManager:
    """配置管理器：统一入口，负责持久化、内存同步、事件通知"""

    def __init__(
        self,
        config: Config,
        event_bus: PublicEventBus,
        secret_store: Any | None = None,
    ):
        self._config = config
        self._event_bus = event_bus
        self._secret_store = secret_store
        self._lock = asyncio.Lock()
        self._last_written_hash: str | None = None
        self._watcher: Any | None = None

    async def update(self, section: str, data: dict) -> dict:
        """更新指定 section 的配置（唯一写入入口）"""
        async with self._lock:
            raw_config = self._load_raw_yaml()

            # 深度合并
            if section not in raw_config or not isinstance(raw_config[section], dict):
                raw_config[section] = {}
            _deep_merge(raw_config[section], data)

            # 展平为 dotted path 用于 secret 处理
            flat_updates = _flatten(data, prefix=section)

            # 处理 secret 路径
            for path, value in flat_updates.items():
                if is_secret_path(path) and self._secret_store is not None:
                    if value:
                        ref = f"agentos/{path}"
                        try:
                            self._secret_store.set(ref, value)
                            _set_nested(raw_config, path, build_secret_ref(ref))
                        except Exception:
                            logger.warning("secret store 不可用，%s 将明文写入 config.yml", path)
                            _set_nested(raw_config, path, value)
                    else:
                        ref = f"agentos/{path}"
                        existing_raw = _get_nested(raw_config, path)
                        if isinstance(existing_raw, str) and is_secret_ref(existing_raw):
                            try:
                                self._secret_store.delete(ref)
                            except Exception:
                                logger.warning("secret store 不可用，跳过删除 %s", path)
                        _set_nested(raw_config, path, "")

            # 写回文件
            self._write_raw_yaml(raw_config)

            # 刷新内存
            self._reload_memory()

            # 构造变更 payload
            changes = {}
            for path, value in flat_updates.items():
                if is_secret_path(path):
                    changes[path] = {"new": _mask_secret(value)}
                else:
                    changes[path] = {"new": value}

            # 发布事件
            if changes:
                event = EventEnvelope(
                    type=CONFIG_UPDATED,
                    session_id=SYSTEM_SESSION_ID,
                    source="system",
                    payload={"section": section, "changes": changes},
                )
                await self._event_bus.publish(event)

            return self.get_section(section)

    def get_section(self, section: str) -> dict:
        """读取指定 section（从内存），secret 脱敏"""
        resolved = deepcopy(self._config.data.get(section, {}))
        raw_config = self._load_raw_yaml()
        raw = deepcopy(raw_config.get(section, {}))
        return _sanitize_section(section, resolved, raw)

    def get_sections(self, sections: list[str]) -> dict:
        """批量读取多个 section"""
        return {s: self.get_section(s) for s in sections}

    # ── 文件监听 ──────────────────────────────────

    def start_file_watcher(self) -> None:
        config_path = self._get_config_path()
        if not config_path:
            logger.warning("无法获取配置文件路径，跳过文件监听")
            return
        try:
            from agentos.platform.config.config_file_watcher import ConfigFileWatcher
            loop = asyncio.get_event_loop()
            self._watcher = ConfigFileWatcher(
                config_path=config_path,
                on_change=self._on_file_changed,
                event_loop=loop,
                get_last_written_hash=lambda: self._last_written_hash,
            )
            self._watcher.start()
            logger.info("ConfigFileWatcher started for %s", config_path)
        except ImportError:
            logger.warning("watchdog 未安装，跳过文件监听")
        except Exception:
            logger.warning("启动文件监听失败", exc_info=True)

    def stop_file_watcher(self) -> None:
        if self._watcher:
            self._watcher.stop()
            self._watcher = None

    async def _on_file_changed(self, changed_sections: dict[str, dict]) -> None:
        async with self._lock:
            self._reload_memory()
            for section, changes in changed_sections.items():
                if changes:
                    event = EventEnvelope(
                        type=CONFIG_UPDATED,
                        session_id=SYSTEM_SESSION_ID,
                        source="system",
                        payload={"section": section, "changes": changes},
                    )
                    await self._event_bus.publish(event)
                    logger.info("Config file changed externally: section=%s", section)

    # ── 内部方法 ──────────────────────────────────

    def _get_config_path(self) -> Path | None:
        path = getattr(self._config, "_config_path", None)
        return path if isinstance(path, Path) else None

    def _load_raw_yaml(self) -> dict[str, Any]:
        config_path = self._get_config_path()
        if not config_path or not config_path.exists():
            return {}
        raw = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        return data if isinstance(data, dict) else {}

    def _write_raw_yaml(self, raw_config: dict[str, Any]) -> None:
        config_path = self._get_config_path()
        if not config_path:
            raise RuntimeError("当前配置实例不支持直接写回 config.yml")
        yaml_text = yaml.dump(
            raw_config, default_flow_style=False, allow_unicode=True, sort_keys=False,
        )
        config_path.write_text(yaml_text, encoding="utf-8")
        self._last_written_hash = hashlib.md5(yaml_text.encode()).hexdigest()

    def _reload_memory(self) -> None:
        if getattr(self._config, "_config_path", None) is not None:
            self._config.data = self._config._load_config()
        else:
            self._config.data = self._config._load_config_from_project_root()


# ── 工具函数 ──────────────────────────────────

def _deep_merge(base: dict, override: dict) -> None:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _flatten(data: dict, prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(_flatten(value, path))
        else:
            result[path] = value
    return result


def _set_nested(target: dict, dotted_path: str, value: Any) -> None:
    keys = dotted_path.split(".")
    current = target
    for key in keys[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    current[keys[-1]] = value


def _get_nested(target: dict, dotted_path: str, default: Any = None) -> Any:
    current: Any = target
    for key in dotted_path.split("."):
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _mask_secret(secret: Any) -> str | None:
    if not isinstance(secret, str) or not secret:
        return None
    if len(secret) <= 8:
        return f"{secret[:2]}...{secret[-2:]}"
    return f"{secret[:4]}...{secret[-4:]}"


def _sanitize_section(path: str, resolved: Any, raw: Any) -> Any:
    if is_secret_path(path):
        return {
            "configured": bool(resolved),
            "masked_value": _mask_secret(resolved),
            "source": _detect_secret_source(raw),
        }
    if isinstance(resolved, dict):
        raw_dict = raw if isinstance(raw, dict) else {}
        return {
            key: _sanitize_section(
                path=f"{path}.{key}", resolved=value, raw=raw_dict.get(key),
            )
            for key, value in resolved.items()
        }
    if isinstance(resolved, list):
        return resolved
    return resolved


def _detect_secret_source(raw_value: Any) -> str:
    if not raw_value:
        return "empty"
    if isinstance(raw_value, str) and is_secret_ref(raw_value):
        return "secret"
    if isinstance(raw_value, str) and raw_value.startswith("${") and raw_value.endswith("}"):
        return "env"
    return "plain"
