from __future__ import annotations

import logging
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# agentos/platform/config/config.py -> 往上 3 层到项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_CONFIG: dict[str, Any] = {
    "system": {
        "log_level": "DEBUG",
        "workspace_dir": "./workspace",
        "database_path": "./var/data/agentos.db",
        "max_concurrent_sessions": 10,
        "granted_paths": [],                         # v1.2: 预授权目录列表
    },
    "server": {
        "host": "0.0.0.0",
        "port": 8000,
        "cors_origins": ["http://localhost:3000", "http://127.0.0.1:3000"],
    },
    "llm_providers": {
        "mock": {
            "api_key": "",
            "base_url": "",
            "default_model": "mock-agent-v1",
            "timeout": 60,
            "max_retries": 1,
        },
        "openai": {
            "api_key": "${OPENAI_API_KEY}",
            "base_url": "${OPENAI_BASE_URL}",
            "default_model": "gpt-4o-mini",
            "timeout": 60,
            "max_retries": 3,
        },
        "anthropic": {
            "api_key": "${ANTHROPIC_API_KEY}",
            "base_url": "${ANTHROPIC_BASE_URL}",
            "default_model": "claude-opus-4-20250514",
            "timeout": 60,
            "max_retries": 3,
        },
        "gemini": {
            "api_key": "${GEMINI_API_KEY}",
            "base_url": "${GEMINI_BASE_URL}",
            "default_model": "gemini-2.5-pro",
            "timeout": 120,
            "max_retries": 3,
        },
    },
    "agent": {
        "provider": "mock",
        "default_model": "mock-agent-v1",
        "default_temperature": 0.2,
        "max_turns_per_session": 50,
        "system_prompt": "你是一个有工具能力的AI助手，请在必要时调用工具。",
    },
    "tools": {
        "bash_command": {"enabled": True, "timeout": 15},
        "serper_search": {"enabled": True, "api_key": "${SERPER_API_KEY}", "timeout": 15, "max_results": 10},
        "fetch_url": {"enabled": True, "timeout": 15, "max_response_mb": 10},
        "file_operations": {
            "enabled": True,
            "timeout": 15,
            "allowed_extensions": [".txt", ".md", ".py", ".json", ".yaml", ".yml", ".ts", ".tsx", ".js", ".jsx"],
        },
        "result_truncation": {
            "max_tokens": 8000,
            "save_dir": "workspace",
        },
        "permission": {
            "enabled": False,
            "auto_approve_levels": ["low"],
            "confirmation_timeout": 60,
        },
    },
    "skills": {
        "extra_dirs": [],
        "entries": {},
    },
    "session": {
        "maintenance": {
            "prune_after_days": 30,
            "max_sessions": 500,
        },
    },
    "bus": {
        "private_bus_ttl": 3600,
        "gc_interval": 60,
    },
    "memory": {
        "enabled": False,
        "bootstrap_max_chars": 8000,
        "search": {
            "enabled": True,
            "embedding_model": "text-embedding-3-small",
            "chunk_size": 400,
            "chunk_overlap": 80,
            "hybrid": {
                "vector_weight": 0.7,
                "text_weight": 0.3,
                "candidate_multiplier": 4,
            },
        },
    },
    "frontend": {
        "backend_ws_url": "ws://localhost:8000/ws",
        "default_theme": "dark",
    },
    "cron": {
        "enabled": True,
        "max_concurrent_runs": 1,
        "retry": {
            "max_attempts": 3,
            "backoff_ms": [60000, 120000, 300000],
        },
        "session_retention": "24h",
        "run_log_max_entries": 2000,
    },
    "heartbeat": {
        "enabled": False,
        "every": "30m",
        "target": "none",
        "to": None,
        "prompt": "Read HEARTBEAT.md if it exists. Follow it strictly. If nothing needs attention, reply HEARTBEAT_OK.",
        "ack_max_chars": 300,
        "light_context": False,
        "active_hours": {
            "start": "08:00",
            "end": "24:00",
            "timezone": "local",
        },
    },
    "plugins": {
        "feishu": {
            "enabled": False,
            "app_id": "",
            "app_secret": "",
            "dm_policy": "open",
            "group_policy": "mention",
            "allowlist": [],
            "log_level": "INFO",
            "render_mode": "card",
            "show_tool_progress": False,
            "api_tool": {
                "enabled": False,
                "allowed_methods": ["GET"],
                "allowed_path_prefixes": [
                    "/open-apis/docx/v1/documents",
                    "/open-apis/wiki/v2/spaces",
                    "/open-apis/drive/v1/files",
                ],
            },
        },
    },
    # v1.0: 多 Agent 配置
    "agents": {},
    "delegation": {
        "max_depth": 3,
        "default_timeout": 300,
        "enabled": True,
    },
}


class Config:
    """从项目根目录的 config.yml 加载配置，与 DEFAULT_CONFIG 深度合并。"""

    def __init__(self, config_path: Path | None = None):
        self._config_path = config_path or PROJECT_ROOT / "config.yml"
        self.data = self._load_config()

    def _load_config(self) -> dict[str, Any]:
        config = deepcopy(DEFAULT_CONFIG)

        if self._config_path.exists():
            with self._config_path.open("r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
            if isinstance(user_config, dict):
                config = self._deep_merge(config, user_config)
                logger.info("Loaded config from %s", self._config_path)
            else:
                logger.warning("配置文件格式错误: %s", self._config_path)
        else:
            logger.warning("配置文件不存在: %s，使用默认配置", self._config_path)

        config = self._resolve_env(config)
        return config

    def _deep_merge(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(base)
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = self._deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    def _resolve_env(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: self._resolve_env(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._resolve_env(v) for v in obj]
        if isinstance(obj, str):
            pattern = re.compile(r"\$\{([^}]+)\}")
            for env_name in pattern.findall(obj):
                obj = obj.replace(f"${{{env_name}}}", os.getenv(env_name, ""))
            return obj
        return obj

    def get(self, path: str, default: Any = None) -> Any:
        value: Any = self.data
        for key in path.split("."):
            if not isinstance(value, dict):
                return default
            value = value.get(key)
            if value is None:
                return default
        return value

    def set(self, path: str, value: Any) -> None:
        """设置运行时配置值（不写入文件）"""
        keys = path.split(".")
        target = self.data
        for key in keys[:-1]:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
            target = target[key]
        target[keys[-1]] = value


config = Config()
logger.info("Config loaded: %s", config)
