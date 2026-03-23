# 配置指南

AgentOS 通过 `config.yml` 配置文件进行全局配置，支持环境变量和系统密钥环引用。本文档详细说明所有配置项及其用法。

## 配置加载优先级

AgentOS 配置加载遵循以下优先级（从高到低）：

```
环境变量覆盖值 > config.yml 中声明的来源（明文 / ${ENV} / ${secret:...}） > 默认值
```

- **环境变量覆盖值**: 最高优先级，适合在 CI/CD 或容器环境中覆盖敏感配置
- **config.yml**: 项目根目录下的配置文件，适合本地开发；敏感字段推荐写成 `${secret:...}` 引用
- **默认值**: 代码中预设的默认值，确保无配置时也能正常启动（使用 mock provider）

## 配置文件位置

配置文件位于项目根目录：

```
agentos/
├── config.yml          ← 配置文件（不入库，需手动创建）
├── config.yml.example  ← 配置示例（入库）
└── ...
```

> **安全提示**: 新增或更新敏感字段时，推荐使用系统 keyring 存储，`config.yml` 仅保留 `${secret:...}` 引用；不要将明文密钥提交到版本库。

## 完整配置结构

### system 段 — 系统配置

```yaml
system:
  # 工作区目录，用于存放 Skills、Workflows 等运行时文件
  workspace_dir: workspace

  # SQLite 数据库路径
  database_path: var/data/agentos.db

  # 日志级别: DEBUG / INFO / WARNING / ERROR
  log_level: DEBUG

  # 授权路径列表，工具只能访问这些路径下的文件
  granted_paths:
    - /home/user/projects
    - /tmp
```

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `workspace_dir` | string | `workspace` | 工作区目录路径 |
| `database_path` | string | `var/data/agentos.db` | SQLite 数据库文件路径 |
| `log_level` | string | `DEBUG` | 日志输出级别 |
| `granted_paths` | list | `[]` | 授权访问的文件系统路径列表 |

### agent 段 — Agent 配置

```yaml
agent:
  # LLM 提供商: openai / anthropic / gemini / mock
  provider: openai

  # 默认模型名称
  default_model: gpt-4o-mini

  # 系统提示词
  system_prompt: "你是一个有用的AI助手"

  # 生成温度 (0.0 - 2.0)
  temperature: 0.7

  # 最大输出 Token 数
  max_tokens: 4096
```

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `provider` | string | `mock` | LLM 提供商，可选 `openai` / `anthropic` / `gemini` / `mock` |
| `default_model` | string | 按 provider 自动选择 | 默认模型。openai 默认 `gpt-4o-mini`，anthropic 默认 `claude-3-sonnet` |
| `system_prompt` | string | `"你是一个有用的AI助手"` | 系统提示词，定义 Agent 的行为和人格 |
| `temperature` | float | `0.7` | 生成温度，值越高输出越随机 |
| `max_tokens` | int | `4096` | 单次 LLM 调用的最大输出 Token 数 |

### llm_providers 段 — LLM 提供商配置

为每个 LLM 提供商配置 API 密钥和基础地址：

```yaml
llm_providers:
  openai:
    api_key: sk-your-openai-api-key
    base_url: https://api.openai.com/v1

  anthropic:
    api_key: sk-ant-your-anthropic-api-key
    base_url: https://api.anthropic.com

  gemini:
    api_key: your-gemini-api-key
    base_url: https://generativelanguage.googleapis.com
```

也可以使用顶层快捷配置（与 `llm_providers.openai` 等价）：

```yaml
OPENAI_API_KEY: sk-your-openai-api-key
OPENAI_BASE_URL: https://api.openai.com/v1
```

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `llm_providers.<provider>.api_key` | string | API 密钥 |
| `llm_providers.<provider>.base_url` | string | API 基础地址，可配置代理或兼容接口 |

### tools 段 — 工具配置

为每个内置工具配置运行参数：

```yaml
tools:
  bash_command:
    # 是否启用
    enabled: true
    # 命令执行超时（秒）
    timeout: 30

  serper_search:
    enabled: true
    # Serper API 密钥
    api_key: ${SERPER_API_KEY}
    # 请求超时（秒）
    timeout: 15
    # 每次搜索最大返回结果数
    max_results: 10

  brave_search:
    enabled: true
    api_key: ${BRAVE_SEARCH_API_KEY}
    timeout: 15
    max_results: 10
    country: US
    search_lang: en
    ui_lang: en-US

  baidu_search:
    enabled: true
    api_key: ${BAIDU_APPBUILDER_API_KEY}
    timeout: 15
    max_results: 10
    search_source: baidu_search_v2

  tavily_search:
    enabled: true
    api_key: ${TAVILY_API_KEY}
    timeout: 15
    max_results: 5
    search_depth: basic
    topic: general

  research_union:
    # research-union 技能在判断主链不足时使用的阈值
    min_sources: 3
    min_topic_coverage: 0.45
    min_valid_evidence: 6
    union_timeout: 90

  fetch_url:
    enabled: true
    # 请求超时（秒）
    timeout: 30

  file_operations:
    enabled: true
    # read_file 和 write_file 的配置
    # 最大读取文件大小（字节）
    max_read_size: 1048576
    # 最大写入文件大小（字节）
    max_write_size: 1048576
```

| 工具 | 配置项 | 类型 | 默认值 | 说明 |
|------|--------|------|--------|------|
| `bash_command` | `enabled` | bool | `true` | 是否启用 Shell 命令执行 |
| `bash_command` | `timeout` | int | `30` | 命令执行超时时间（秒） |
| `serper_search` | `enabled` | bool | `true` | 是否启用网络搜索 |
| `serper_search` | `api_key` | string | — | Serper API 密钥 |
| `serper_search` | `timeout` | int | `15` | 搜索请求超时时间（秒） |
| `serper_search` | `max_results` | int | `10` | 最大搜索结果数 |
| `brave_search` | `api_key` | string | — | Brave Search API 密钥 |
| `brave_search` | `timeout` | int | `15` | 搜索请求超时时间（秒） |
| `brave_search` | `max_results` | int | `10` | 最大搜索结果数 |
| `brave_search` | `country/search_lang/ui_lang` | string | `US/en/en-US` | Brave 搜索地域与语言偏好 |
| `baidu_search` | `api_key` | string | — | 百度 AppBuilder API 密钥 |
| `baidu_search` | `timeout` | int | `15` | 搜索请求超时时间（秒） |
| `baidu_search` | `max_results` | int | `10` | 最大搜索结果数 |
| `baidu_search` | `search_source` | string | `baidu_search_v2` | 百度搜索源 |
| `tavily_search` | `api_key` | string | — | Tavily API 密钥 |
| `tavily_search` | `timeout` | int | `15` | 搜索请求超时时间（秒） |
| `tavily_search` | `max_results` | int | `5` | 最大搜索结果数 |
| `tavily_search` | `search_depth/topic/time_range` | string | `basic/general/""` | Tavily 搜索深度、主题、时间范围 |
| `research_union` | `min_sources` | int | `3` | 最少来源数（不足时触发 union 补充） |
| `research_union` | `min_topic_coverage` | float | `0.45` | 主题覆盖率阈值 |
| `research_union` | `min_valid_evidence` | int | `6` | 最少有效证据条数（title+link） |
| `research_union` | `union_timeout` | int | `90` | union 补充阶段超时（秒） |
| `fetch_url` | `enabled` | bool | `true` | 是否启用网页抓取 |
| `fetch_url` | `timeout` | int | `30` | 请求超时时间（秒） |
| `file_operations` | `enabled` | bool | `true` | 是否启用文件读写 |

#### 搜索工具 API Key 获取方式

AgentOS 的 Tools 页面会直接展示以下步骤，用户不需要只依赖外部文档链接：

| 工具 | 获取步骤 |
|------|----------|
| `serper_search` | 打开 `https://serper.dev/` 注册并登录，进入 `Dashboard`，在 `API Key` 区域复制 key。 |
| `brave_search` | 打开 `https://api-dashboard.search.brave.com/app/documentation/web-search/get-started` 登录控制台，在 `Subscriptions` 订阅 `Web Search` plan，再复制 `X-Subscription-Token`。 |
| `baidu_search` | 打开百度千帆快速开始文档并进入 `控制台-安全认证-API Key`，创建 API Key，勾选千帆 / AppBuilder / AI 搜索权限后复制 key；请求时按 `Bearer <api_key>` 使用。 |
| `tavily_search` | 登录 `https://tavily.com/`，进入 `Dashboard / API Keys` 区域复制 key；请求时按 `Authorization: Bearer <api_key>` 使用。 |

### tools.permission 段 — 工具权限配置

```yaml
tools:
  permission:
    # 是否启用权限确认
    enabled: true

    # 自动批准的安全等级列表
    # safe: 只读操作（如 read_file, serper_search）
    # moderate: 有副作用但可控的操作（如 write_file）
    # dangerous: 高风险操作（如 bash_command）
    auto_approve_levels:
      - safe

    # 权限确认超时时间（秒），超时默认拒绝
    confirmation_timeout: 30
```

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enabled` | bool | `true` | 是否启用工具执行前的权限确认 |
| `auto_approve_levels` | list | `["safe"]` | 自动批准的安全等级 |
| `confirmation_timeout` | int | `30` | 用户确认超时时间（秒） |

### cron 段 — 定时任务配置

```yaml
cron:
  # 是否启用 Cron 调度器
  enabled: false
```

### heartbeat 段 — 心跳配置

```yaml
heartbeat:
  # 是否启用心跳
  enabled: false

  # 心跳间隔（秒）
  every: 3600

  # 心跳触发时发送的提示词
  prompt: "请检查是否有待处理的任务"
```

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enabled` | bool | `false` | 是否启用定时心跳 |
| `every` | int | `3600` | 心跳间隔（秒） |
| `prompt` | string | — | 心跳触发时的提示词 |

### memory 段 — 记忆系统配置

```yaml
memory:
  # 是否启用长期记忆
  enabled: false

  search:
    # 是否启用语义搜索
    enabled: false
```

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enabled` | bool | `false` | 是否启用长期记忆系统 |
| `search.enabled` | bool | `false` | 是否启用记忆的语义搜索功能 |

## 环境变量覆盖

以下环境变量可覆盖 `config.yml` 中的对应配置：

```bash
# LLM 密钥
export OPENAI_API_KEY=sk-your-key
export OPENAI_BASE_URL=https://api.openai.com/v1
export ANTHROPIC_API_KEY=sk-ant-your-key

# 工具密钥
export SERPER_API_KEY=your-serper-key

# 系统配置
export LOG_LEVEL=DEBUG
```

环境变量命名规则：大写字母 + 下划线分隔，与 `config.yml` 中的顶层键名对应。

## 多 Agent 配置

AgentOS 支持配置多个 Agent，每个 Agent 拥有独立的模型、提示词和工具配置。

### 在 config.yml 中配置

```yaml
agents:
  default:
    provider: openai
    default_model: gpt-4o-mini
    system_prompt: "你是一个通用AI助手"
    tools:
      - bash_command
      - read_file
      - write_file

  researcher:
    provider: openai
    default_model: gpt-4o
    system_prompt: "你是一个专业的研究分析师，擅长信息检索和总结"
    tools:
      - serper_search
      - fetch_url
      - read_file

  coder:
    provider: anthropic
    default_model: claude-3-sonnet
    system_prompt: "你是一个资深的软件工程师，擅长代码编写和调试"
    tools:
      - bash_command
      - read_file
      - write_file
```

### 使用 Agent 配置文件

也可以在 `workspace/agents/` 目录下创建独立的 Agent 配置文件：

```
workspace/
└── agents/
    ├── researcher.json
    ├── coder.json
    └── writer.json
```

Agent JSON 配置示例 (`workspace/agents/researcher.json`)：

```json
{
  "name": "researcher",
  "description": "专业研究分析师",
  "provider": "openai",
  "default_model": "gpt-4o",
  "system_prompt": "你是一个专业的研究分析师...",
  "tools": ["serper_search", "fetch_url", "read_file"],
  "temperature": 0.3
}
```

## 完整示例配置

以下是一个包含常用配置的完整 `config.yml` 示例：

```yaml
# ============================
# AgentOS 配置文件
# ============================

# --- LLM API 密钥 ---
OPENAI_API_KEY: sk-your-openai-api-key
OPENAI_BASE_URL: https://api.openai.com/v1
SERPER_API_KEY: your-serper-api-key

# --- 系统配置 ---
system:
  workspace_dir: workspace
  database_path: var/data/agentos.db
  log_level: DEBUG
  granted_paths:
    - /home/user/projects

# --- Agent 配置 ---
agent:
  provider: openai
  default_model: gpt-4o-mini
  system_prompt: "你是一个有用的AI助手，可以帮助用户完成各种任务。"
  temperature: 0.7
  max_tokens: 4096

# --- 工具配置 ---
tools:
  bash_command:
    enabled: true
    timeout: 30

  serper_search:
    api_key: ${SERPER_API_KEY}
    timeout: 15
    max_results: 10

  fetch_url:
    enabled: true
    timeout: 30

  file_operations:
    enabled: true

  permission:
    enabled: true
    auto_approve_levels:
      - safe
    confirmation_timeout: 30

# --- 定时任务 ---
cron:
  enabled: false

# --- 心跳 ---
heartbeat:
  enabled: false
  every: 3600
  prompt: "请检查是否有待处理的任务"

# --- 记忆系统 ---
memory:
  enabled: false
  search:
    enabled: false
```

## 配置变量引用

在 `config.yml` 中可以使用两种引用语法：

```yaml
tools:
  serper_search:
    api_key: ${SERPER_API_KEY}   # 从环境变量读取

llm:
  providers:
    openai:
      api_key: ${secret:agentos/llm.providers.openai.api_key}  # 从系统 keyring 读取
```

说明：

- `${VAR_NAME}`：从环境变量读取
- `${secret:agentos/<dotted_path>}`：从系统 keyring 读取
- 第一版敏感字段默认覆盖 `llm.providers.*.api_key`、`tools.*.api_key`、`tools.email.password`、`plugins.feishu.app_secret`、`plugins.wecom.secret`
- 如果 keyring backend 不可用，secret 写入会失败，不会自动回退到明文

## 明文迁移到 keyring

如果你已有历史明文配置，可以显式触发迁移：

```bash
agentos migrate-secrets
```

也可以通过 HTTP API 触发：

```http
POST /api/config/migrate-secrets
```

迁移行为：

- 只迁移已登记的敏感路径
- 已经是 `${secret:...}` 的值会跳过
- `${ENV}` 环境变量引用会跳过
- 迁移成功后，`config.yml` 中的明文会改写成 `${secret:agentos/<dotted_path>}`

## 下一步

- 返回 [快速开始](quickstart.md) 了解启动步骤
- 阅读 [架构设计](../architecture/) 深入理解系统设计
