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
        "brave_search": {
            "enabled": True,
            "api_key": "${BRAVE_SEARCH_API_KEY}",
            "timeout": 15,
            "max_results": 10,
            "country": "US",
            "search_lang": "en",
            "ui_lang": "en-US",
            "extra_snippets": False,
        },
        "baidu_search": {
            "enabled": True,
            "api_key": "${BAIDU_APPBUILDER_API_KEY}",
            "timeout": 15,
            "max_results": 10,
            "search_source": "baidu_search_v2",
            "search_recency_filter": "",
        },
        "tavily_search": {
            "enabled": True,
            "api_key": "${TAVILY_API_KEY}",
            "timeout": 15,
            "max_results": 5,
            "search_depth": "basic",
            "topic": "general",
            "time_range": "",
            "project_id": "",
        },
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
        "retry": {
            "max_retries": 0,
            "backoff_seconds": [0, 1, 3],
        },
        "enabled": True,
    },
}


class Config:
    """从项目根目录的 config.yml 加载配置，与 DEFAULT_CONFIG 深度合并。

    支持两种初始化方式：
    1. 传统方式：Config(config_path=...)，直接指定单个配置文件路径
    2. 新方式：Config(project_root=..., user_config_dir=...)，自动发现配置文件
       - 从 project_root 向上遍历，收集所有 .agentos/config.yaml（从远到近）
       - 同时加载沿途发现的 config.yml（遗留格式，含 OPENAI_API_KEY 等顶层 key）
       - user_config_dir 用于测试时避免加载真实用户配置
    """

    def __init__(
        self,
        config_path: Path | None = None,
        *,
        project_root: Path | None = None,
        user_config_dir: Path | None = None,
    ):
        # 新方式：通过 project_root 自动发现配置
        if project_root is not None:
            self._project_root = Path(project_root).resolve()
            self._user_config_dir = Path(user_config_dir) if user_config_dir is not None else None
            self._config_path = None  # 新方式不使用单一路径
            self.data = self._load_config_from_project_root()
        else:
            # 兼容旧方式：单一 config_path
            self._config_path = config_path or PROJECT_ROOT / "config.yml"
            self._project_root = None
            self._user_config_dir = None
            self.data = self._load_config()

    def _load_config_from_project_root(self) -> dict[str, Any]:
        """新方式配置加载：从 project_root 向上遍历，收集所有配置文件后合并。"""
        config = deepcopy(DEFAULT_CONFIG)

        # 收集从 project_root 到文件系统根目录的所有路径（从远到近）
        dirs: list[Path] = []
        current = self._project_root
        while True:
            dirs.append(current)
            parent = current.parent
            if parent == current:
                break
            current = parent
        # 从远到近排列（最远的祖先先应用，近的后覆盖）
        dirs.reverse()

        # 遗留格式（config.yml 含顶层 key）按从远到近收集
        legacy_data: dict[str, Any] = {}
        # .agentos/config.yaml 按从远到近收集
        agentos_configs: list[dict[str, Any]] = []

        for d in dirs:
            # 尝试加载遗留 config.yml
            legacy_path = d / "config.yml"
            if legacy_path.exists():
                with legacy_path.open("r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f) or {}
                if isinstance(raw, dict):
                    legacy_data = self._deep_merge(legacy_data, raw)
                    logger.info("加载遗留配置: %s", legacy_path)

            # 尝试加载 .agentos/config.yaml
            agentos_path = d / ".agentos" / "config.yaml"
            if agentos_path.exists():
                with agentos_path.open("r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f) or {}
                if isinstance(raw, dict):
                    agentos_configs.append(raw)
                    logger.info("加载项目配置: %s", agentos_path)

        # 先应用遗留配置中的 legacy key 映射
        config = self._apply_legacy_keys(config, legacy_data)

        # 再依次应用 .agentos/config.yaml（从远到近，近的覆盖远的）
        for agentos_cfg in agentos_configs:
            config = self._deep_merge(config, agentos_cfg)

        # 如果 .agentos/config.yaml 中显式设置了 provider，
        # 则根据最终 provider 填充 agent.default_model（若仍是默认值则更新）
        config = self._sync_provider_defaults(config)

        config = self._resolve_env(config)
        return config

    def _apply_legacy_keys(self, config: dict[str, Any], legacy: dict[str, Any]) -> dict[str, Any]:
        """将遗留 config.yml 中的顶层 key 映射到新结构，不覆盖已由 .agentos/config.yaml 设置的 provider。"""
        result = deepcopy(config)

        # OPENAI_BASE_URL -> llm_providers.openai.base_url
        if "OPENAI_BASE_URL" in legacy and legacy["OPENAI_BASE_URL"]:
            result["llm_providers"]["openai"]["base_url"] = legacy["OPENAI_BASE_URL"]

        # OPENAI_API_KEY -> llm_providers.openai.api_key
        if "OPENAI_API_KEY" in legacy and legacy["OPENAI_API_KEY"]:
            result["llm_providers"]["openai"]["api_key"] = legacy["OPENAI_API_KEY"]
            # 只有当前 provider 未被显式覆盖时（仍为默认 mock），才自动切换到 openai
            if result["agent"]["provider"] == DEFAULT_CONFIG["agent"]["provider"]:
                result["agent"]["provider"] = "openai"
                result["agent"]["default_model"] = result["llm_providers"]["openai"]["default_model"]

        # SERPER_API_KEY -> tools.serper_search.api_key
        if "SERPER_API_KEY" in legacy and legacy["SERPER_API_KEY"]:
            result["tools"]["serper_search"]["api_key"] = legacy["SERPER_API_KEY"]

        # BRAVE_SEARCH_API_KEY -> tools.brave_search.api_key
        if "BRAVE_SEARCH_API_KEY" in legacy and legacy["BRAVE_SEARCH_API_KEY"]:
            result["tools"]["brave_search"]["api_key"] = legacy["BRAVE_SEARCH_API_KEY"]

        # BAIDU_APPBUILDER_API_KEY -> tools.baidu_search.api_key
        if "BAIDU_APPBUILDER_API_KEY" in legacy and legacy["BAIDU_APPBUILDER_API_KEY"]:
            result["tools"]["baidu_search"]["api_key"] = legacy["BAIDU_APPBUILDER_API_KEY"]

        # TAVILY_API_KEY -> tools.tavily_search.api_key
        if "TAVILY_API_KEY" in legacy and legacy["TAVILY_API_KEY"]:
            result["tools"]["tavily_search"]["api_key"] = legacy["TAVILY_API_KEY"]

        # MODEL -> agent.default_model 以及 llm_providers.openai.default_model
        if "MODEL" in legacy and legacy["MODEL"]:
            result["agent"]["default_model"] = legacy["MODEL"]
            result["llm_providers"]["openai"]["default_model"] = legacy["MODEL"]

        return result

    def _sync_provider_defaults(self, config: dict[str, Any]) -> dict[str, Any]:
        """根据最终确定的 provider 同步 agent.default_model。

        如果 agent.default_model 的值与当前 provider 不匹配，
        但恰好等于某个其他 provider 的默认模型，则说明它是由遗留映射或中间合并写入的，
        应更新为当前 provider 的默认模型。
        """
        result = deepcopy(config)
        provider = result["agent"]["provider"]
        current_model = result["agent"]["default_model"]

        # 收集所有 provider 的默认模型集合
        all_provider_defaults = {
            p_cfg.get("default_model")
            for p_cfg in result.get("llm_providers", {}).values()
            if isinstance(p_cfg, dict) and "default_model" in p_cfg
        }

        # 若当前 default_model 是某个 provider 的默认值（包括当前 provider），
        # 则将其对齐到当前 provider 的默认模型
        if current_model in all_provider_defaults:
            provider_defaults = result.get("llm_providers", {}).get(provider, {})
            if "default_model" in provider_defaults:
                result["agent"]["default_model"] = provider_defaults["default_model"]
        return result

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
