from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from agentos.platform.config.config import config


def setup_logging() -> None:
    level_name = str(config.get("system.log_level", "DEBUG")).upper()
    level = getattr(logging, level_name, logging.DEBUG)

    from agentos.platform.config.workspace import resolve_agentos_home
    home = resolve_agentos_home(config)
    log_dir = home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(filename)s | %(message)s")

    file_handler = RotatingFileHandler(log_dir / "system.log", maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)
