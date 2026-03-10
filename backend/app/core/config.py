from __future__ import annotations

import logging
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


DEFAULT_CONFIG: dict[str, Any] = {
    "system": {
        "log_level": "DEBUG",
        "workspace_dir": "./SenseAssistant/workspace",
        "database_path": "./SenseAssistant/agentos.db",
        "max_concurrent_sessions": 10,
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
            "max_tokens": 8000,             # Token 截断阈值（ToolRuntime 层）
            "save_dir": "workspace",        # 完整结果保存目录
        },
        "permission": {
            "enabled": False,               # 是否启用权限管理
            "auto_approve_levels": ["low"], # 自动批准的风险等级
            "confirmation_timeout": 60,     # 确认超时时间（秒）
        },
    },
    "skills": {
        "entries": {},
    },
    "session": {
        "maintenance": {
            "prune_after_days": 30,
            "max_sessions": 500,
        },
    },
    "bus": {
        "private_bus_ttl": 3600,    # 私有总线存活时间（秒），超时未活跃则回收
        "gc_interval": 60,          # GC 扫描间隔（秒）
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
}


class Config:
    def __init__(self, project_root: Path | None = None, user_config_dir: Path | None = None):
        self.project_root = project_root or Path.cwd()
        self._user_config_dir = user_config_dir if user_config_dir is not None else Path.home() / ".SenseAssistant"
        self.data = self._load_config()

    def _load_yaml_if_exists(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"配置文件格式错误: {path}")
        return raw

    def _load_config(self) -> dict[str, Any]:
        config = deepcopy(DEFAULT_CONFIG)
        provider_configured = False
        default_model_configured = False

        user_config = self._user_config_dir / "config.yaml"
        user_override = self._load_yaml_if_exists(user_config)
        if user_override:
            logger.info(f"Loaded user config from {user_config}")
        provider_configured = provider_configured or self._has_path(user_override, ("agent", "provider"))
        default_model_configured = default_model_configured or self._has_path(user_override, ("agent", "default_model"))

        config = self._deep_merge(config, user_override)

        # 按目录层级加载项目配置：父目录先合并，子目录后覆盖。
        for project_dir in reversed(self._project_dirs()):
            project_config = project_dir / ".agentos" / "config.yaml"
            project_override = self._load_yaml_if_exists(project_config)
            if project_override:
                logger.info(f"Loaded project config from {project_config}")
            provider_configured = provider_configured or self._has_path(project_override, ("agent", "provider"))
            default_model_configured = default_model_configured or self._has_path(
                project_override, ("agent", "default_model")
            )
            config = self._deep_merge(config, project_override)

        config = self._resolve_env(config)

        # 兼容旧版 config.yml：同样按目录层级合并，子目录优先级更高。
        for project_dir in reversed(self._project_dirs()):
            legacy_path = project_dir / "config.yml"
            if legacy_path.exists():
                logger.info(f"Loaded legacy config from {legacy_path}")
                with legacy_path.open("r", encoding="utf-8") as f:
                    legacy = yaml.safe_load(f) or {}
                if isinstance(legacy, dict):
                    self._apply_legacy_config(
                        config,
                        legacy,
                        provider_configured=provider_configured,
                        default_model_configured=default_model_configured,
                    )

        if not default_model_configured:
            provider_name = str(config.get("agent", {}).get("provider", ""))
            provider_default_model = str(config.get("llm_providers", {}).get(provider_name, {}).get("default_model", ""))
            if provider_default_model:
                config.setdefault("agent", {})["default_model"] = provider_default_model
        return config

    def _project_dirs(self) -> list[Path]:
        dirs: list[Path] = []
        current = self.project_root.resolve()
        while True:
            dirs.append(current)
            if current.parent == current:
                break
            current = current.parent
        return dirs

    def _apply_legacy_config(
        self,
        config: dict[str, Any],
        legacy: dict[str, Any],
        *,
        provider_configured: bool,
        default_model_configured: bool,
    ) -> None:
        openai = config.setdefault("llm_providers", {}).setdefault("openai", {})
        if legacy.get("OPENAI_BASE_URL"):
            openai["base_url"] = legacy["OPENAI_BASE_URL"]
        has_openai_key = bool(legacy.get("OPENAI_API_KEY"))
        if has_openai_key:
            openai["api_key"] = legacy["OPENAI_API_KEY"]
            if not provider_configured:
                config.setdefault("agent", {})["provider"] = "openai"
        if legacy.get("SERPER_API_KEY"):
            config.setdefault("tools", {}).setdefault("serper_search", {})["api_key"] = legacy["SERPER_API_KEY"]
        model_name = self._pick_legacy_model_name(legacy)
        if model_name:
            openai["default_model"] = model_name
            if not default_model_configured:
                config.setdefault("agent", {})["default_model"] = model_name

    def _pick_legacy_model_name(self, legacy: dict[str, Any]) -> str:
        value = legacy.get("MODEL")
        if value is not None:
            model_name = str(value).strip()
            if model_name:
                return model_name
        return ""

    def _has_path(self, obj: dict[str, Any], path: tuple[str, ...]) -> bool:
        current: Any = obj
        for key in path:
            if not isinstance(current, dict) or key not in current:
                return False
            current = current[key]
        return True

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


config = Config()
logger.info(f"Config loaded: {config}")