# AgentOS

> 基于事件驱动架构的 AI Agent 平台

AgentOS 是一个开源的 AI Agent 运行平台，采用事件驱动架构，支持 Web、CLI、TUI 多种接入方式。它提供了完整的 Agent 运行时、工具系统、Skills 编排和多渠道接入能力，帮助开发者快速构建和部署智能 Agent 应用。

## 核心特性

- **事件驱动架构** — 所有模块通过 PublicEventBus 解耦通信，事件封装为 `EventEnvelope`，支持会话隔离和全链路追踪
- **多 Agent 协作** — 支持多 Agent 配置与协作，灵活编排复杂任务流程
- **工具系统** — 内置 10 个工具（Shell 命令、4 种搜索引擎、网页抓取、文件读写、多 Agent 协作），支持通过装饰器自定义扩展
- **Skills 编排** — 声明式任务编排机制，16 个内置 Skills 覆盖文档处理、前端开发等场景
- **多渠道接入** — 统一 Gateway 架构，支持 WebSocket、CLI/TUI、飞书等多种 Channel
- **插件化扩展** — LLM 提供商、Channel、存储、工具均可插件化替换

## 技术栈

| 层级 | 技术选型 |
|------|----------|
| 后端框架 | FastAPI + Python 3.12 + asyncio |
| 数据库 | SQLite |
| 前端框架 | Next.js 14 + TypeScript |
| 实时通信 | WebSocket |
| Python 包管理 | uv |
| Node.js 包管理 | npm |

## 六层架构

AgentOS 采用清晰的六层架构设计，各层职责明确、边界分明：

```
┌─────────────────────────────────────────────┐
│  interfaces    HTTP REST API / WebSocket     │  ← 对外协议层
├─────────────────────────────────────────────┤
│  adapters      LLM / Channel / Storage       │  ← 外部系统适配层
├─────────────────────────────────────────────┤
│  capabilities  Tools / Skills / Memory       │  ← 能力层
├─────────────────────────────────────────────┤
│  kernel        EventBus / Runtime / Scheduler│  ← 核心运行时
├─────────────────────────────────────────────┤
│  platform      Config / Logging / Security   │  ← 平台基础设施
├─────────────────────────────────────────────┤
│  app           Gateway / CLI / Web           │  ← 应用入口
└─────────────────────────────────────────────┘
```

**各层职责：**

- **interfaces** — 对外暴露 HTTP REST API 和 WebSocket 端点，处理协议转换
- **adapters** — 适配 LLM 提供商（OpenAI / Anthropic / Gemini）、Channel（WebSocket / 飞书）、存储等外部系统
- **capabilities** — 提供工具调用、Skills 编排、记忆管理等 Agent 核心能力
- **kernel** — 核心事件总线、Agent / LLM / Tool Runtime 调度引擎
- **platform** — 配置加载、日志系统、路径安全策略等基础设施
- **app** — 后端 Gateway 入口、CLI / TUI 客户端、Next.js 前端应用

## 事件流概览

AgentOS 中一次完整的用户交互，事件流转如下：

```
user.input
  → agent.step_started
    → llm.call_requested
      → llm.call_completed
        → tool.call_requested (如果模型调用了工具)
          → tool.call_completed
    → agent.step_completed
```

所有事件通过 `session_id` 进行会话隔离，通过 `turn_id` 标识对话轮次，通过 `trace_id` 关联请求与响应。

## 核心 Runtime 模块

| 模块 | 职责 | 监听事件 | 发布事件 |
|------|------|----------|----------|
| AgentRuntime | 对话流程编排 | `user.input` | `agent.step_started` / `agent.step_completed` |
| LLMRuntime | LLM 调用管理 | `llm.call_requested` | `llm.call_completed` |
| ToolRuntime | 工具执行管理 | `tool.call_requested` | `tool.call_completed` |
| TitleRuntime | 会话标题生成 | `agent.step_completed` | — |

## 快速导航

- [快速开始](guide/quickstart.md) — 环境准备、安装配置、启动运行
- [配置指南](guide/configuration.md) — 配置文件详解、环境变量、多 Agent 配置
- [架构设计](architecture/) — 事件驱动架构、六层架构、Gateway 设计
- [核心模块](core/) — Runtime、EventBus、状态管理
- [能力系统](capabilities/) — 工具系统、Skills 编排、记忆系统
- [适配器](adapters/) — LLM 提供商、Channel、存储适配
- [API 参考](api/) — REST API、WebSocket 协议
- [开发指南](dev/) — 测试、日志、贡献指南

## 内置工具

| 工具名 | 功能 |
|--------|------|
| `bash_command` | 执行 Shell 命令 |
| `serper_search` | 网络搜索（需要 SERPER_API_KEY） |
| `brave_search` | 网络搜索（需要 BRAVE_SEARCH_API_KEY） |
| `baidu_search` | 网络搜索（需要 BAIDU_APPBUILDER_API_KEY） |
| `tavily_search` | 网络搜索（需要 TAVILY_API_KEY） |
| `fetch_url` | 获取网页内容 |
| `read_file` | 读取文件内容 |
| `write_file` | 写入文件内容 |
| `create_agent` | 动态创建新 Agent 配置 |
| `send_message` | 向其他 Agent 发送消息（Gateway 启动时注册） |

工具通过 `ToolRegistry` 注册，支持自定义扩展。

## Skills 系统

16 个内置 Skills 提供声明式任务编排能力：

- **文档处理**: `pdf_to_markdown`、`docx_to_markdown`、`xlsx_to_markdown`
- **前端开发**: `design_frontend`、`test_frontend`
- **Skill 管理**: `create_skill`

Skills 通过 YAML 配置定义，支持多步骤编排和条件分支。

## 版本信息

当前版本: **v0.5**

| 版本 | 主要变更 |
|------|----------|
| v0.5 | 代码架构重组（六层架构）、移除 Workflow 模块、完整测试覆盖（734 tests） |
| v0.4 | Skills 系统（16 个内置 Skills）、Skills 配置管理 |
| v0.2 | Gateway 架构、CLI/TUI 客户端、自动标题生成、工具结果截断、消息归一化 |

**暂不支持**: 流式响应、Token 管理、用户认证、沙箱执行
