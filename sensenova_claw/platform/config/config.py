from __future__ import annotations

import logging
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from sensenova_claw.platform.secrets.refs import is_secret_ref, parse_secret_ref
from sensenova_claw.platform.secrets.store import SecretStoreError, build_default_secret_store

logger = logging.getLogger(__name__)

# sensenova_claw/platform/config/config.py -> 往上 3 层到项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# 默认配置文件路径：~/.sensenova-claw/config.yml
DEFAULT_CONFIG_PATH = Path.home() / ".sensenova-claw" / "config.yml"

DEFAULT_CONFIG: dict[str, Any] = {
    "system": {
        "log_level": "DEBUG",
        "sensenova_claw_home": "${SENSENOVA_CLAW_HOME}",           # 默认 ~/.sensenova-claw，支持环境变量覆盖
        "workspace_dir": "",                          # 已废弃，由 sensenova_claw_home 替代
        "database_path": "",                          # 空=自动用 {sensenova_claw_home}/data/sensenova-claw.db
        "max_concurrent_sessions": 10,
        "granted_paths": [],                         # v1.2: 预授权目录列表
    },
    "server": {
        "host": "0.0.0.0",
        "port": 8000,
        "cors_origins": ["http://localhost:3000", "http://127.0.0.1:3000"],
    },
    "llm": {
        "providers": {
            "mock": {
                "api_key": "",
                "base_url": "",
                "timeout": 60,
                "max_retries": 1,
            },
            "openai": {
                "api_key": "${OPENAI_API_KEY}",
                "base_url": "${OPENAI_BASE_URL}",
                "timeout": 60,
                "max_retries": 3,
            },
            "anthropic": {
                "api_key": "${ANTHROPIC_API_KEY}",
                "base_url": "${ANTHROPIC_BASE_URL}",
                "timeout": 60,
                "max_retries": 3,
            },
            "gemini": {
                "api_key": "${GEMINI_API_KEY}",
                "base_url": "${GEMINI_BASE_URL}",
                "timeout": 120,
                "max_retries": 3,
            },
        },
        "models": {
            "mock": {
                "provider": "mock",
                "model_id": "mock-agent-v1",
            },
            "gpt-5.4": {
                "provider": "openai",
                "model_id": "gpt-5.4",
                "timeout": 60,
                "max_tokens": 128000,
                "max_output_tokens": 16384,
            },
            "claude-sonnet": {
                "provider": "anthropic",
                "model_id": "claude-sonnet-4-6",
                "timeout": 60,
                "max_tokens": 128000,
                "max_output_tokens": 16384,
            },
            "claude-opus": {
                "provider": "anthropic",
                "model_id": "claude-opus-4-6",
                "timeout": 60,
                "max_tokens": 128000,
                "max_output_tokens": 16384,
            },
            "gemini-pro": {
                "provider": "gemini",
                "model_id": "gemini-2.5-pro",
                "timeout": 120,
                "max_tokens": 128000,
                "max_output_tokens": 16384,
            },
        },
        "default_model": "mock",  # 引用 llm.models 中的 key
    },
    # agent 段保留作为所有 agent 的后备默认值
    "agent": {
        "temperature": 0.2,
        "max_turns_per_session": 50,
        "system_prompt": "你是一个有工具能力的AI助手，请在必要时调用工具。",
    },
    "tools": {
        "bash_command": {"enabled": True, "timeout": 15},
        "serper_search": {"enabled": True, "api_key": "${SERPER_API_KEY}", "timeout": 15, "max_results": 10},
        "brave_search": {"enabled": True, "api_key": "${BRAVE_API_KEY}", "timeout": 15, "max_results": 10},
        "baidu_search": {"enabled": True, "timeout": 15, "max_results": 10},
        "tavily_search": {"enabled": True, "api_key": "${TAVILY_API_KEY}", "timeout": 15, "max_results": 10},
        "fetch_url": {"enabled": True, "timeout": 15, "max_response_mb": 10},
        "file_operations": {
            "enabled": True,
            "timeout": 15,
            "allowed_extensions": [".txt", ".md", ".py", ".json", ".yaml", ".yml", ".ts", ".tsx", ".js", ".jsx"],
        },
        "email": {
            "enabled": False,
            "smtp_host": "",
            "smtp_port": 587,
            "imap_host": "",
            "imap_port": 993,
            "username": "${EMAIL_USERNAME}",
            "password": "${EMAIL_PASSWORD}",
            "max_attachment_size_mb": 10,
            "timeout": 30,
        },
        "ask_user": {"enabled": True, "timeout": 300},
        "result_truncation": {
            "max_tokens": 8000,
            "save_dir": "workspace",
        },
        "permission": {
            "enabled": False,
            "auto_approve_levels": ["low"],
            "confirmation_timeout": 60,
            "timeout_action": "reject",  # reject | approve | block
        },
    },
    "skills": {
        "extra_dirs": [],
        "entries": {},
    },
    "context_compression": {
        "max_context_tokens": 128000,
        "phase1_threshold": 0.8,
        "phase2_trigger": 0.6,
        "phase2_chunk_ratio": 0.3,
        "user_input_max_tokens": 1000,
        "tool_summary_max_tokens": 3000,
        "phase2_merge_max_tokens": 2000,
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
    "notification": {
        "enabled": True,
        "channels": ["browser", "session"],
        "native": {"enabled": False},
        "browser": {"enabled": True},
        "electron": {"enabled": False},
        "session": {"enabled": True},
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
        "wecom": {
            "enabled": False,
            "bot_id": "",
            "secret": "",
            "websocket_url": "wss://openws.work.weixin.qq.com",
            "dm_policy": "open",
            "group_policy": "open",
            "allowlist": [],
            "group_allowlist": [],
            "show_tool_progress": False,
        },
        "whatsapp": {
            "enabled": False,
            "auth_dir": "",
            "dm_policy": "open",
            "group_policy": "open",
            "allowlist": [],
            "group_allowlist": [],
            "show_tool_progress": False,
            "bridge": {
                "command": "node",
                "entry": "",
                "startup_timeout_seconds": 30,
                "send_timeout_seconds": 15,
            },
        },
    },
        "miniapps": {
            "default_builder": "builtin",
            "acp": {
                "enabled": False,
                "command": "",
                "args": [],
                "env": {},
                "startup_timeout_seconds": 20,
                "request_timeout_seconds": 180,
            },
        },
    # 安全与认证配置（Jupyter-lab 风格 token）
    "security": {
        "auth_enabled": False,  # 启用后所有 API/WebSocket 需要 token 认证
    },
    # Agent 配置（dict 格式，每个 key 是 agent id）
    "agents": {
        "default": {
            "name": "Default Agent",
            "description": "默认 AI Agent",
            "model": "mock",
            "temperature": 0.2,
            "tools": [],
            "skills": [],
        },
    },
    "delegation": {
        "max_depth": 3,
        "default_timeout": 300,
        "max_tool_calls": 30,
        "max_llm_calls": 15,
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
       - 从 project_root 向上遍历，收集所有 .sensenova-claw/config.yaml（从远到近）
       - 同时加载沿途发现的 config.yml（遗留格式，含 OPENAI_API_KEY 等顶层 key）
       - user_config_dir 用于测试时避免加载真实用户配置
    """

    def __init__(
        self,
        config_path: Path | None = None,
        *,
        project_root: Path | None = None,
        user_config_dir: Path | None = None,
        secret_store: Any | None = None,
    ):
        self._secret_store = secret_store or build_default_secret_store()
        # 新方式：通过 project_root 自动发现配置
        if project_root is not None:
            self._project_root = Path(project_root).resolve()
            self._user_config_dir = Path(user_config_dir) if user_config_dir is not None else None
            self._config_path = None  # 新方式不使用单一路径
            self.data = self._load_config_from_project_root()
        else:
            # 默认配置路径：~/.sensenova-claw/config.yml
            self._config_path = config_path or DEFAULT_CONFIG_PATH
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
        # .sensenova-claw/config.yaml 按从远到近收集
        sensenova_claw_configs: list[dict[str, Any]] = []

        for d in dirs:
            # 尝试加载遗留 config.yml
            legacy_path = d / "config.yml"
            if legacy_path.exists():
                with legacy_path.open("r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f) or {}
                if isinstance(raw, dict):
                    legacy_data = self._deep_merge(legacy_data, raw)
                    logger.info("加载遗留配置: %s", legacy_path)

            # 尝试加载 .sensenova-claw/config.yaml
            sensenova_claw_path = d / ".sensenova-claw" / "config.yaml"
            if sensenova_claw_path.exists():
                with sensenova_claw_path.open("r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f) or {}
                if isinstance(raw, dict):
                    sensenova_claw_configs.append(raw)
                    logger.info("加载项目配置: %s", sensenova_claw_path)

        # 先应用遗留配置中的 legacy key 映射
        config = self._apply_legacy_keys(config, legacy_data)

        # 再依次应用 .sensenova-claw/config.yaml（从远到近，近的覆盖远的）
        for sensenova_claw_cfg in sensenova_claw_configs:
            config = self._deep_merge(config, sensenova_claw_cfg)

        config = self._resolve_env(config)
        return config

    def _apply_legacy_keys(self, config: dict[str, Any], legacy: dict[str, Any]) -> dict[str, Any]:
        """将遗留 config.yml 中的顶层环境变量 key 映射到新结构。旧格式直接报错。"""
        self._validate_config_format(legacy)
        result = deepcopy(config)

        # 顶层环境变量快捷 key（非旧格式，保留支持）
        if "OPENAI_BASE_URL" in legacy and legacy["OPENAI_BASE_URL"]:
            result["llm"]["providers"]["openai"]["base_url"] = legacy["OPENAI_BASE_URL"]

        if "OPENAI_API_KEY" in legacy and legacy["OPENAI_API_KEY"]:
            result["llm"]["providers"]["openai"]["api_key"] = legacy["OPENAI_API_KEY"]
            if result["llm"]["default_model"] == DEFAULT_CONFIG["llm"]["default_model"]:
                result["llm"]["default_model"] = "gpt-5.4"
                result["agent"]["model"] = "gpt-5.4"

        if "SERPER_API_KEY" in legacy and legacy["SERPER_API_KEY"]:
            result["tools"]["serper_search"]["api_key"] = legacy["SERPER_API_KEY"]

        return result

    def _load_config(self) -> dict[str, Any]:
        config = deepcopy(DEFAULT_CONFIG)

        if self._config_path.exists():
            with self._config_path.open("r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
            if isinstance(user_config, dict):
                self._validate_config_format(user_config)
                config = self._deep_merge(config, user_config)
                logger.info("Loaded config from %s", self._config_path)
            else:
                logger.warning("配置文件格式错误: %s", self._config_path)
        else:
            logger.warning("配置文件不存在: %s，使用默认配置", self._config_path)

        config = self._resolve_env(config)
        return config

    @staticmethod
    def _validate_config_format(user_config: dict[str, Any]) -> None:
        """检查配置格式是否为新格式，旧格式直接报错"""
        errors: list[str] = []

        if "llm_providers" in user_config:
            errors.append(
                "'llm_providers' 已废弃，请改为 'llm.providers'。"
                "参考 config_example.yml 中的新格式。"
            )

        agent = user_config.get("agent", {})
        if isinstance(agent, dict):
            if "provider" in agent:
                errors.append(
                    "'agent.provider' 已废弃。"
                    "请在 agents.<id>.model 中引用 llm.models 中的 key，provider 由系统自动解析。"
                )
            if "default_model" in agent:
                errors.append(
                    "'agent.default_model' 已废弃，请改为 'llm.default_model'。"
                )
            if "model" in agent:
                logger.warning("'agent.model' 已废弃，请改为 'llm.default_model'。")
            if "default_temperature" in agent:
                errors.append(
                    "'agent.default_temperature' 已废弃，请改为 'agent.temperature'。"
                )

        agents = user_config.get("agents")
        if isinstance(agents, list):
            errors.append(
                "'agents' 不再支持 id 列表格式，请改为 dict 格式。"
                "参考 config_example.yml 中的 agents 配置。"
            )

        if errors:
            msg = "配置文件格式不兼容:\n" + "\n".join(f"  - {e}" for e in errors)
            raise ValueError(msg)

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
            return self._resolve_string_value(obj)
        return obj

    def _resolve_string_value(self, value: str) -> str:
        if is_secret_ref(value):
            if self._secret_store is None:
                return ""
            if hasattr(self._secret_store, "is_available") and not self._secret_store.is_available():
                logger.warning("secret store 不可用，跳过解析 %s", value)
                return ""
            ref = parse_secret_ref(value)
            try:
                secret = self._secret_store.get(ref)
            except SecretStoreError as exc:
                logger.warning("secret 读取失败，跳过解析 %s: %s", value, exc)
                return ""
            return secret or ""
        pattern = re.compile(r"\$\{([^}]+)\}")
        for env_name in pattern.findall(value):
            value = value.replace(f"${{{env_name}}}", os.getenv(env_name, ""))
        return value

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

    def resolve_model(self, model_key: str | None = None) -> tuple[str, str]:
        """解析模型 key 为 (provider_name, model_id)。

        优先从 llm.models 注册表查找；如果 model_key 不在注册表中，
        则视为直接的 model_id（向后兼容），从注册表中反查 provider。

        Args:
            model_key: llm.models 中的 key（如 "claude-sonnet"），
                       为 None 时使用 llm.default_model。
        Returns:
            (provider_name, model_id) 元组
        """
        if not model_key:
            model_key = self.get("llm.default_model") or None

        models = self.get("llm.models", {})

        # default_model 未设置时，自动选取第一个有有效 api_key 的 model
        if not model_key:
            for key, entry in models.items():
                if not isinstance(entry, dict):
                    continue
                provider_name = entry.get("provider", "")
                provider_cfg = self.get(f"llm.providers.{provider_name}", {})
                api_key = str(provider_cfg.get("api_key", ""))
                if api_key and not api_key.startswith("${"):
                    logger.info("default_model 未设置，自动选用: %s (provider=%s)", key, provider_name)
                    return provider_name, entry.get("model_id", key)
            logger.warning("没有找到任何已配置 api_key 的模型，使用 mock provider")
            return "mock", "mock"

        # 精确匹配 models 注册表
        if model_key in models:
            entry = models[model_key]
            return entry.get("provider", "mock"), entry.get("model_id", model_key)

        # 向后兼容：model_key 可能是直接的 model_id（如 "gpt-4o-mini"）
        # 从 models 注册表中反查
        for _key, entry in models.items():
            if isinstance(entry, dict) and entry.get("model_id") == model_key:
                return entry.get("provider", "mock"), model_key

        # 都找不到，返回 mock
        logger.warning("未知的模型 key: %s，使用 mock provider", model_key)
        return "mock", model_key

    def get_model_max_output_tokens(self, model_key: str | None = None) -> int:
        """获取模型配置中的 max_output_tokens（最大输出 token 数）。

        Args:
            model_key: llm.models 中的 key，为 None 时使用 llm.default_model。
        Returns:
            max_output_tokens，无配置时返回默认值 16384
        """
        if not model_key:
            model_key = self.get("llm.default_model", "mock")
        models = self.get("llm.models", {})
        if model_key in models:
            return int(models[model_key].get("max_output_tokens", 16384))
        # 向后兼容：反查 model_id
        for _key, entry in models.items():
            if isinstance(entry, dict) and entry.get("model_id") == model_key:
                return int(entry.get("max_output_tokens", 16384))
        return 16384

    def get_model_extra_body(self, model_key: str | None = None) -> dict:
        """获取模型配置中的 extra_body（透传给 LLM API 请求体的额外参数）。

        Args:
            model_key: llm.models 中的 key，为 None 时使用 llm.default_model。
        Returns:
            extra_body dict，无配置时返回空 dict
        """
        if not model_key:
            model_key = self.get("llm.default_model", "mock")
        models = self.get("llm.models", {})
        if model_key in models:
            return dict(models[model_key].get("extra_body", {}))
        # 向后兼容：反查 model_id
        for _key, entry in models.items():
            if isinstance(entry, dict) and entry.get("model_id") == model_key:
                return dict(entry.get("extra_body", {}))
        return {}


config = Config()
logger.info("Config loaded: %s", config)
