"""ConfigFileWatcher — 监听 config.yml 文件变化，外部编辑也触发联动。"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class ConfigFileWatcher:
    """监听 config.yml 文件变化

    防误触发:
    1. 防抖（1秒）— 多次文件事件只处理最后一次
    2. 内容 hash 比对 — 无实质变更或自写时跳过
    """

    def __init__(
        self,
        config_path: Path,
        on_change: Callable[[dict[str, dict]], Awaitable[None]],
        event_loop: asyncio.AbstractEventLoop,
        get_last_written_hash: Callable[[], str | None],
        debounce_seconds: float = 1.0,
    ):
        self._config_path = config_path
        self._on_change = on_change
        self._event_loop = event_loop
        self._get_last_written_hash = get_last_written_hash
        self._debounce_seconds = debounce_seconds
        self._observer: Any = None
        self._debounce_timer: threading.Timer | None = None
        self._last_known_hash: str | None = self._compute_file_hash()
        self._cached_config: dict | None = self._load_yaml_safe()

    def start(self) -> None:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        watcher = self

        class Handler(FileSystemEventHandler):
            def on_modified(self, event):
                if event.is_directory:
                    return
                if Path(event.src_path).resolve() == watcher._config_path.resolve():
                    watcher._schedule_debounce()

        self._observer = Observer()
        self._observer.schedule(Handler(), str(self._config_path.parent), recursive=False)
        self._observer.start()

    def stop(self) -> None:
        if self._debounce_timer:
            self._debounce_timer.cancel()
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)

    def _schedule_debounce(self) -> None:
        if self._debounce_timer:
            self._debounce_timer.cancel()
        self._debounce_timer = threading.Timer(
            self._debounce_seconds, self._on_debounced
        )
        self._debounce_timer.start()

    def _on_debounced(self) -> None:
        new_hash = self._compute_file_hash()
        if new_hash is None:
            return
        if new_hash == self._last_known_hash:
            return
        last_written = self._get_last_written_hash()
        if last_written and new_hash == last_written:
            self._last_known_hash = new_hash
            return
        self._last_known_hash = new_hash
        new_config = self._load_yaml_safe()
        if new_config is None:
            logger.warning("config.yml YAML 解析失败，跳过本次变更")
            return
        changed = self._diff_sections(new_config)
        self._cached_config = new_config
        if changed:
            asyncio.run_coroutine_threadsafe(
                self._on_change(changed), self._event_loop
            )

    def _compute_file_hash(self) -> str | None:
        try:
            content = self._config_path.read_bytes()
            return hashlib.md5(content).hexdigest()
        except Exception:
            return None

    def _load_yaml_safe(self) -> dict | None:
        try:
            text = self._config_path.read_text(encoding="utf-8")
            data = yaml.safe_load(text)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _diff_sections(self, new_config: dict) -> dict[str, dict]:
        old = self._cached_config or {}
        changed: dict[str, dict] = {}
        all_sections = set(list(old.keys()) + list(new_config.keys()))
        for section in all_sections:
            old_val = old.get(section)
            new_val = new_config.get(section)
            if old_val != new_val:
                changes = {}
                if isinstance(new_val, dict):
                    flat = _flatten_for_diff(new_val, section)
                    for path, value in flat.items():
                        changes[path] = {"new": value}
                else:
                    changes[section] = {"new": new_val}
                changed[section] = changes
        return changed


def _flatten_for_diff(data: dict, prefix: str) -> dict:
    result = {}
    for key, value in data.items():
        path = f"{prefix}.{key}"
        if isinstance(value, dict):
            result.update(_flatten_for_diff(value, path))
        else:
            result[path] = value
    return result
