# 配置文件设计

## 配置文件位置

- 主配置文件: `~/.SenseAssistant/config.yaml`
- 项目配置: `<project_root>/.agentos/config.yaml` (可选)

## 配置文件结构

### 完整配置示例

```yaml
# AgentOS 配置文件

# 系统配置
system:
  log_level: INFO                    # DEBUG/INFO/WARNING/ERROR
  workspace_dir: ~/.SenseAssistant/workspace
  database_path: ~/.SenseAssistant/agentos.db
  max_concurrent_sessions: 10

# 服务器配置
server:
  host: 0.0.0.0
  port: 8000
  cors_origins:
    - http://localhost:3000
    - http://127.0.0.1:3000

# LLM 提供商配置
llm_providers:
  openai:
    api_key: sk-xxx                  # OpenAI API Key
    base_url: https://api.openai.com/v1
    default_model: gpt-4
    timeout: 60
    max_retries: 3

  anthropic:
    api_key: sk-ant-xxx              # Anthropic API Key
    base_url: https://api.anthropic.com
    default_model: claude-3-5-sonnet-20241022
    timeout: 60
    max_retries: 3

# 默认 Agent 配置
agent:
  default_model: gpt-4
  default_temperature: 0.7
  max_turns_per_session: 50
  system_prompt: |
    You are a helpful AI assistant with access to various tools.
    Always think step by step and use tools when necessary.

# 工具配置
tools:
  bash_command:
    enabled: true
    timeout: 15
    allowed_commands: []             # 空列表表示允许所有命令
    blocked_commands:                # 黑名单
      - rm -rf /
      - mkfs

  serper_search:
    enabled: true
    api_key: xxx                     # Serper API Key
    timeout: 15
    max_results: 10

  fetch_url:
    enabled: true
    timeout: 15
    max_size_mb: 10
    allowed_domains: []              # 空列表表示允许所有域名

  file_operations:
    enabled: true
    timeout: 15
    max_file_size_mb: 50
    allowed_extensions:
      - .txt
      - .py
      - .js
      - .ts
      - .md
      - .json
      - .yaml
      - .yml
    blocked_paths:                   # 禁止访问的路径
      - /etc/passwd
      - /etc/shadow

# 数据库配置
database:
  auto_cleanup: true
  archive_sessions_after_days: 30
  delete_events_after_days: 90
  backup_enabled: false
  backup_interval_hours: 24

# 前端配置
frontend:
  default_theme: dark
  enable_file_browser: true
  enable_history: true
  max_message_length: 10000
```

## 配置加载逻辑

### 配置优先级

1. 项目配置 (`.agentos/config.yaml`)
2. 用户配置 (`~/.SenseAssistant/config.yaml`)
3. 默认配置 (代码中的默认值)

### 配置加载器

```python
import yaml
from pathlib import Path
from typing import Any

class Config:
    def __init__(self):
        self.data = self._load_config()

    def _load_config(self) -> dict:
        # 默认配置
        config = self._get_default_config()

        # 加载用户配置
        user_config_path = Path.home() / ".SenseAssistant" / "config.yaml"
        if user_config_path.exists():
            with open(user_config_path) as f:
                user_config = yaml.safe_load(f)
                config = self._merge_config(config, user_config)

        # 加载项目配置
        project_config_path = Path.cwd() / ".agentos" / "config.yaml"
        if project_config_path.exists():
            with open(project_config_path) as f:
                project_config = yaml.safe_load(f)
                config = self._merge_config(config, project_config)

        return config

    def _merge_config(self, base: dict, override: dict) -> dict:
        """递归合并配置"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = value
        return result

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值，支持点号分隔的路径"""
        keys = key.split('.')
        value = self.data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default
```

## 环境变量支持

配置文件中可以使用环境变量：

```yaml
llm_providers:
  openai:
    api_key: ${OPENAI_API_KEY}
```

### 环境变量解析

```python
import os
import re

def resolve_env_vars(config: dict) -> dict:
    """解析配置中的环境变量"""
    if isinstance(config, dict):
        return {k: resolve_env_vars(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [resolve_env_vars(item) for item in config]
    elif isinstance(config, str):
        # 匹配 ${VAR_NAME} 格式
        pattern = r'\$\{([^}]+)\}'
        matches = re.findall(pattern, config)
        for var_name in matches:
            env_value = os.getenv(var_name, '')
            config = config.replace(f'${{{var_name}}}', env_value)
        return config
    else:
        return config
```

## 配置验证

### 验证器

```python
from pydantic import BaseModel, Field

class LLMProviderConfig(BaseModel):
    api_key: str
    base_url: str
    default_model: str
    timeout: int = 60
    max_retries: int = 3

class ToolConfig(BaseModel):
    enabled: bool = True
    timeout: int = 15

class ConfigSchema(BaseModel):
    system: dict
    server: dict
    llm_providers: dict[str, LLMProviderConfig]
    agent: dict
    tools: dict[str, ToolConfig]

def validate_config(config: dict) -> bool:
    try:
        ConfigSchema(**config)
        return True
    except Exception as e:
        print(f"配置验证失败: {e}")
        return False
```

## 配置热更新

支持在运行时重新加载配置（部分配置项）：

```python
class ConfigManager:
    def __init__(self):
        self.config = Config()
        self.watchers = []

    def reload(self):
        """重新加载配置"""
        old_config = self.config.data
        self.config = Config()
        self._notify_watchers(old_config, self.config.data)

    def watch(self, callback):
        """注册配置变更监听器"""
        self.watchers.append(callback)

    def _notify_watchers(self, old_config, new_config):
        for callback in self.watchers:
            callback(old_config, new_config)
```
