<div align="center">
  <h1>AgentOS</h1>
  <p><strong>基于事件驱动架构的 AI Agent 平台</strong></p>
  <p>
    <img src="https://img.shields.io/badge/python-≥3.12-blue" alt="Python">
    <img src="https://img.shields.io/badge/node-≥18-green" alt="Node.js">
    <img src="https://img.shields.io/badge/version-v0.5-orange" alt="Version">
    <img src="https://img.shields.io/badge/license-MIT-brightgreen" alt="License">
  </p>
  <p>
    支持 Web、CLI、TUI、飞书、WhatsApp 多种接入方式 · 多 LLM Provider · 多 Agent 编排 · Skills 市场 · 记忆系统
  </p>
</div>

## Key Features

- **事件驱动架构** — 所有模块通过 PublicEventBus 解耦通信，支持会话级隔离
- **多 Provider 支持** — OpenAI / Anthropic / Gemini / 自定义，一键切换
- **多 Agent 编排** — 动态创建子 Agent，支持委托调用和配置继承
- **Skills 市场** — 声明式任务编排，支持从 ClawHub 安装/更新/卸载
- **多渠道接入** — Web (Next.js) / CLI / TUI / 飞书 / WhatsApp，统一 Gateway 架构
- **工具系统** — 内置 bash / 搜索 / 文件读写 / URL 抓取，支持权限管理
- **记忆系统** — 向量检索 + 文本搜索混合模式，跨会话持久记忆
- **定时任务** — Cron 表达式 / 间隔 / 一次性任务，支持心跳巡检

## 🏗️ Architecture

[todo: architecture_diagram]

**事件流**:
```
ui.user_input → agent.step_started → llm.call_requested → llm.call_completed
  → tool.call_requested → tool.call_completed → agent.step_completed
```

**核心模块**:

| 层级 | 模块 | 职责 |
|------|------|------|
| **Kernel** | EventBus, Runtime, Scheduler, Heartbeat | 事件通信、运行时编排、定时调度 |
| **Capabilities** | Agents, Tools, Skills, Memory | 多 Agent、工具执行、技能编排、记忆 |
| **Adapters** | LLM, Channels, Storage, Plugins | LLM 对接、渠道适配、持久化、插件 |
| **Interfaces** | HTTP API, WebSocket | REST 接口、WebSocket 实时通信 |
| **Platform** | Config, Logging, Security | 配置管理、日志、路径安全策略 |
| **App** | Gateway, CLI, Web | 应用入口、命令行、前端 |

## Table of Contents

- [Key Features](#key-features)
- [Architecture](#️-architecture)
- [Install](#-install)
- [Quick Start](#-quick-start)
- [Configuration](#️-configuration)
- [Chat Channels](#-chat-channels)
- [LLM Providers](#-llm-providers)
- [Tools](#-tools)
- [Skills](#-skills)
- [CLI Reference](#-cli-reference)
- [Project Structure](#-project-structure)
- [Testing](#-testing)
- [Contribute & Roadmap](#-contribute--roadmap)

## 📦 Install

**环境要求**:
- Python 3.12+
- Node.js 18+
- npm

**安装依赖**:

```bash
git clone https://github.com/SenseTime-FVG/agentos.git
cd agentos

# Python 依赖
uv sync          # 或 pip install -e .

# 前端依赖
cd agentos/app/web && npm install && cd -

# 根目录 Playwright（可选，用于前端 e2e 测试）
npm install
```

## 🚀 Quick Start

**1. 配置 API Key**

```bash
cp config_example.yml config.yml
# 编辑 config.yml，填入 LLM provider 和工具的 API Key
```

**2. 一键启动**

```bash
npm run dev
```

- Web 前端: http://localhost:3000
- API 后端: http://localhost:8000

**3. 单独启动**

```bash
# 启动 API 服务
npm run dev:server

# 启动 Web 前端
npm run dev:web

# 启动 CLI 客户端（需后端已运行）
python3 -m agentos.app.cli.cli_client --port 8000
```

**4. 发送第一条消息**

打开 http://localhost:3000，在对话框中输入消息即可开始对话。

## ⚙️ Configuration

配置文件 `config.yml` 位于项目根目录（不入库）：

```yaml
# LLM 提供商
llm_providers:
  openai:
    api_key: sk-xxx
    base_url: https://api.openai.com/v1
    default_model: gpt-4o
  anthropic:
    api_key: sk-ant-xxx
    base_url: https://api.anthropic.com
    default_model: claude-sonnet-4-6
  gemini:
    api_key: xxx
    base_url: https://generativelanguage.googleapis.com/v1
    default_model: gemini-2.5-pro

# Agent 配置
agent:
  provider: openai           # 当前使用的 provider
  default_model: gpt-4o      # 默认模型
  system_prompt: "你是一个有工具能力的AI助手"

# 工具配置
tools:
  serper_search:
    api_key: xxx              # Serper 搜索 API Key
    max_results: 10
  brave_search:
    api_key: xxx              # Brave Search API Key
    max_results: 10
  baidu_search:
    api_key: xxx              # Baidu AppBuilder API Key
    max_results: 10
  tavily_search:
    api_key: xxx              # Tavily API Key
    max_results: 5
```

**配置加载优先级**: 环境变量 > `.agentos/config.yaml` > `config.yml` > 默认值

## 💬 Chat Channels

通过 Gateway 统一管理多渠道接入，每个 Channel 独立管理会话。

| 渠道 | 说明 | 配置 |
|------|------|------|
| **Web** | Next.js 14 前端，WebSocket 实时通信 | 默认启用 |
| **CLI** | 命令行交互客户端 | `python3 -m agentos.app.cli.cli_client` |
| **飞书** | 企业 IM 集成，支持私聊/群聊 | `config.yml` plugins.feishu |
| **WhatsApp** | 核心版 WhatsApp Web 文本接入 | `config.yml` plugins.whatsapp |

<details>
<summary><b>飞书配置</b></summary>

```yaml
plugins:
  feishu:
    enabled: true
    app_id: "cli_xxx"
    app_secret: "xxx"
    dm_policy: "open"          # 私聊策略: open / allowlist
    group_policy: "mention"    # 群聊策略: mention / open / disabled
```

启动 Gateway 后飞书机器人自动连接。

</details>

<details>
<summary><b>WhatsApp 配置</b></summary>

```yaml
plugins:
  whatsapp:
    enabled: true
    auth_dir: ".agentos/data/channels/whatsapp/auth"
    dm_policy: "open"          # 私聊策略: open / allowlist / disabled
    group_policy: "open"       # 群聊策略: open / allowlist / disabled
    allowlist: []              # 私聊允许名单，支持 +15550000001 或 JID
    group_allowlist: []        # 群聊允许名单，使用群 JID
    show_tool_progress: false
    bridge:
      command: "node"
      entry: "agentos/adapters/channels/whatsapp/bridge/src/index.mjs"
      startup_timeout_seconds: 30
      send_timeout_seconds: 15
```

安装 sidecar 依赖：

```bash
npm install --prefix agentos/adapters/channels/whatsapp/bridge
```

当前仓库的 WhatsApp runtime 通过 Node sidecar + Baileys 提供；若未安装 sidecar 依赖，Python channel 只能完成协议层启动，无法真正连接 WhatsApp Web。

</details>

## 🤖 LLM Providers

| Provider | 配置字段 | 说明 |
|----------|----------|------|
| **OpenAI** | `llm_providers.openai` | GPT-4o, GPT-4o-mini 等 |
| **Anthropic** | `llm_providers.anthropic` | Claude Sonnet/Opus 等 |
| **Gemini** | `llm_providers.gemini` | Gemini Pro 等 |
| **Mock** | 内置 | 测试用，无需 API Key |

切换 Provider 只需修改 `config.yml`:

```yaml
agent:
  provider: anthropic
  default_model: claude-sonnet-4-6
```

<details>
<summary><b>添加新 Provider（开发者指南）</b></summary>

1. 在 `agentos/adapters/llm/providers/` 下创建 `xxx_provider.py`
2. 继承 `LLMProvider` 基类，实现 `async def call()` 方法
3. 在 `agentos/adapters/llm/factory.py` 的 `LLMFactory` 中注册
4. 在 `config.yml` 的 `llm_providers` 中添加配置

</details>

## 🔧 Tools

内置工具：

| 工具 | 风险等级 | 说明 |
|------|---------|------|
| `bash_command` | HIGH | 执行 shell 命令 |
| `serper_search` | LOW | 网络搜索（需 Serper API Key） |
| `brave_search` | LOW | 网络搜索（需 Brave Search API Key） |
| `baidu_search` | LOW | 网络搜索（需 Baidu AppBuilder API Key） |
| `tavily_search` | LOW | 网络搜索（需 Tavily API Key） |
| `fetch_url` | LOW | 抓取网页内容 |
| `read_file` | LOW | 读取文件 |
| `write_file` | MEDIUM | 写入/追加/插入文件 |

**权限管理**:

```yaml
tools:
  permission:
    enabled: true
    auto_approve_levels: ["low"]     # 自动批准低风险工具
    confirmation_timeout: 60         # 高风险工具等待用户确认（秒）
```

**路径安全策略**: `PathPolicy` 限制文件操作在 workspace 目录内，防止越权访问。

## 🎯 Skills

Skills 是声明式任务编排机制，通过 YAML 配置定义多步骤工作流。

**内置 Skills**:
- 文档处理: `pdf_to_markdown`, `docx_to_markdown`, `xlsx_to_markdown`
- 前端开发: `design_frontend`, `test_frontend`
- Skill 管理: `create_skill`

**从市场安装**:

通过 Web 界面的 Skills 管理页面搜索并安装 ClawHub 市场中的 Skills。

<details>
<summary><b>创建自定义 Skill</b></summary>

在 `workspace/skills/` 下创建目录，包含 `SKILL.md`：

```markdown
---
name: my-skill
description: 我的自定义技能
arguments:
  - name: target
    description: 目标参数
---

请根据 $ARGUMENTS 执行以下步骤：

1. 分析需求
2. 执行操作
3. 返回结果
```

</details>

## 💻 CLI Reference

| 命令 | 说明 |
|------|------|
| `npm run dev` | 一键启动前后端 |
| `npm run dev:server` | 启动 API 服务 |
| `npm run dev:web` | 启动 Web 前端 |
| `npm run test` | 运行全部测试 |
| `npm run test:unit` | 运行单元测试 |
| `npm run test:e2e` | 运行 e2e 测试 |
| `npm run test:web:e2e` | 运行前端 e2e 测试 |

**CLI 客户端**:

```bash
python3 -m agentos.app.cli.cli_client [OPTIONS]

Options:
  --host TEXT       服务地址（默认: localhost）
  --port INT        端口号（默认: 8000）
  --agent TEXT      Agent ID
  --session TEXT    恢复指定 session
  --debug           显示调试信息
  -e, --execute TEXT  执行单条消息后退出
```

**交互命令**: `/quit` 退出, `/` 打开命令菜单

## 📁 Project Structure

```
agentos/
├── kernel/              # 🧠 内核层
│   ├── events/          #    事件总线（PublicEventBus, PrivateEventBus）
│   ├── runtime/         #    运行时编排（Agent/LLM/Tool Worker）
│   ├── scheduler/       #    Cron 定时调度
│   └── heartbeat/       #    心跳巡检
├── capabilities/        # 💎 能力层
│   ├── agents/          #    多 Agent 配置与注册
│   ├── tools/           #    工具系统（builtin + 编排）
│   ├── skills/          #    Skills 注册与市场
│   └── memory/          #    记忆系统（向量 + 文本）
├── adapters/            # 🔌 适配层
│   ├── llm/             #    LLM Providers（OpenAI/Anthropic/Gemini）
│   ├── channels/        #    渠道适配（WebSocket/飞书/WhatsApp）
│   ├── storage/         #    SQLite 仓储
│   ├── skill_sources/   #    Skill 市场适配器
│   └── plugins/         #    插件系统
├── interfaces/          # 🌐 接口层
│   ├── http/            #    REST API 端点
│   └── ws/              #    WebSocket Gateway
├── platform/            # ⚙️ 平台层
│   ├── config/          #    配置加载与管理
│   ├── logging/         #    日志系统
│   └── security/        #    路径安全策略
└── app/                 # 🚀 应用层
    ├── gateway/         #    FastAPI 入口（main.py）
    ├── cli/             #    CLI/TUI 客户端
    └── web/             #    Next.js 前端

tests/                   # ✅ 测试（unit/integration/e2e/cross_feature）
workspace/               # 📂 运行时工作区（skills, 数据）
docs/                    # 📖 技术文档
scripts/                 # 🛠️ 开发脚本
```

## ✅ Testing

```bash
# 全部测试
npm run test              # 或 python3 -m pytest tests/ -q

# 按类型
npm run test:unit         # 单元测试
npm run test:e2e          # 后端 e2e
npm run test:web:e2e      # 前端 Playwright e2e

# 跳过慢速测试（真实 API 调用）
python3 -m pytest tests/ -q -m "not slow"

# ask_user 真实 API 回归（后端事件链）
./.venv/bin/python tests/e2e/run_ask_user_real_api.py --provider gemini --timeout 120

# ask_user 前端回归脚本（需先安装 Playwright 浏览器与系统依赖）
cd agentos/app/web && PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-browsers npx playwright test e2e/ask-user.spec.ts --reporter=line
```

**测试体系**:

| 类型 | 目录 | 说明 |
|------|------|------|
| 单元测试 | `tests/unit/` | 真实组件测试，无 mock |
| 集成测试 | `tests/integration/` | 跨模块集成验证 |
| E2E 测试 | `tests/e2e/` | 全链路端到端 |
| 交叉特性 | `tests/cross_feature/` | 跨特性交互验证 |

所有 LLM 测试同时覆盖 mock_provider + 真实 API（config.yml 中有 key 的 provider）。

## 🤝 Contribute & Roadmap

欢迎提交 PR！

**Roadmap**:

- [ ] 流式响应
- [ ] Token 用量管理
- [ ] 用户认证与权限
- [ ] 沙箱执行环境
- [ ] 更多渠道集成（钉钉等）
- [ ] 更多 Skill 市场源

[todo: contributors_badge]

---

<p align="center">
  <sub>AgentOS is for educational, research, and technical exchange purposes.</sub>
</p>
