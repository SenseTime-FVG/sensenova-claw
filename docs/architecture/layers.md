# 六层分层架构

AgentOS v0.5 采用六层分层架构，代码组织在 `agentos/` 目录下。各层之间遵循严格的依赖方向：**外层可以依赖内层，内层不依赖外层**。

```
┌─────────────────────────────────────────────┐
│                  app/                        │  应用入口层
├─────────────────────────────────────────────┤
│               interfaces/                    │  接口层
├──────────────────────┬──────────────────────┤
│     adapters/        │    capabilities/      │  适配层 / 能力层
├──────────────────────┴──────────────────────┤
│                 kernel/                      │  核心内核层
├─────────────────────────────────────────────┤
│                platform/                     │  平台基础层
└─────────────────────────────────────────────┘
```

依赖方向：`app → interfaces → adapters/capabilities → kernel → platform`

---

## 1. platform/ - 平台基础层

最底层的基础设施，提供跨模块共用的平台能力，不依赖任何上层模块。

| 子模块 | 职责 |
|--------|------|
| `config/` | 配置加载。优先级：环境变量 > `config.yml` > 默认值 |
| `logging/` | 日志系统。开发模式输出 DEBUG 级别日志，包含 LLM 输入、工具执行详情、事件流转追踪 |
| `security/` | 安全策略。`PathPolicy` 控制文件路径访问权限，拒绝列表防止危险操作 |

---

## 2. kernel/ - 核心内核层

AgentOS 的核心引擎，包含事件系统和 Runtime 机制。

### kernel/events/ - 事件系统

| 组件 | 职责 |
|------|------|
| `EventEnvelope` | 事件信封，统一的事件数据结构，包含 event_id、type、session_id、payload 等字段 |
| `PublicEventBus` | 全局事件总线，基于 `asyncio.Queue` 实现的发布-订阅系统 |
| `PrivateEventBus` | 会话级事件总线，每个 session 一个实例，物理隔离会话事件流 |
| `BusRouter` | 事件路由器，根据 `session_id` 将 PublicEventBus 的事件路由到对应 PrivateEventBus |
| `EventPersister` | 事件持久化，独立订阅 PublicEventBus，将所有事件写入 SQLite |

### kernel/runtime/ - Runtime 模块

| 组件 | 对应 Worker | 职责 |
|------|-------------|------|
| `AgentRuntime` | `AgentSessionWorker` | 对话流程编排，监听 `user.input`，发布 `agent.step_*` |
| `LLMRuntime` | `LLMSessionWorker` | LLM 调用管理，监听 `llm.call_requested`，发布 `llm.call_completed` |
| `ToolRuntime` | `ToolSessionWorker` | 工具执行，监听 `tool.call_requested`，发布 `tool.call_completed` |
| `TitleRuntime` | - | 自动生成会话标题，订阅 `agent.step_completed` |

### kernel/scheduler/ - 调度系统

| 组件 | 职责 |
|------|------|
| `CronRuntime` | 定时任务调度，支持 cron 表达式，管理定时任务的增删改查和执行 |

### kernel/heartbeat/ - 心跳系统

| 组件 | 职责 |
|------|------|
| `HeartbeatRuntime` | 心跳检测，定期检查系统状态和活跃会话 |

---

## 3. capabilities/ - 能力层

提供 Agent 的各种能力，是可扩展的功能模块。

### capabilities/tools/ - 工具系统

| 组件 | 职责 |
|------|------|
| `Tool`（基类） | 工具抽象基类，定义工具接口 |
| `ToolRegistry` | 工具注册表，通过 `@tool_registry.register()` 装饰器注册工具 |
| 内置工具 (`builtin.py`) | 多个内置工具：`bash_command`、`serper_search`、`brave_search`、`baidu_search`、`tavily_search`、`fetch_url`、`read_file`、`write_file` |

### capabilities/skills/ - Skills 系统

| 组件 | 职责 |
|------|------|
| `SkillRegistry` | Skill 注册表，加载 workspace 和内置 skills |
| `Skill` | 声明式任务编排，通过 YAML 配置定义多步骤任务流程 |

16 个内置 skills 包括文档处理（`pdf_to_markdown`、`docx_to_markdown`、`xlsx_to_markdown`）、前端开发（`design_frontend`、`test_frontend`）、Skill 管理（`create_skill`）等。

### capabilities/agents/ - 多 Agent 配置

| 组件 | 职责 |
|------|------|
| `AgentRegistry` | Agent 配置注册表，从 `config.yml` 和 `workspace/agents/` 加载 |
| `AgentConfig` | Agent 配置定义，包含模型、系统提示、工具列表等 |

### capabilities/memory/ - 记忆系统

| 组件 | 职责 |
|------|------|
| `MemoryManager` | 记忆管理，负责 `MEMORY.md` 的读写和注入 |

---

## 4. adapters/ - 适配层

外部依赖的适配和抽象，隔离第三方服务的具体实现。

### adapters/llm/ - LLM 提供商适配

| 组件 | 职责 |
|------|------|
| `LLMFactory` | LLM 提供商工厂，根据配置创建对应的 provider |
| `OpenAIProvider` | OpenAI 适配（含兼容 API 网关） |
| `AnthropicProvider` | Anthropic Claude 适配 |
| `GeminiProvider` | Google Gemini 适配 |
| `MockProvider` | 测试用 Mock 提供商 |

### adapters/channels/ - 接入渠道适配

| 组件 | 职责 |
|------|------|
| `WebSocketChannel` | WebSocket 接入，管理 WebSocket 连接和消息收发 |
| `FeishuChannel` | 飞书机器人接入（通过插件加载） |

### adapters/storage/ - 数据库仓储

| 组件 | 职责 |
|------|------|
| `Repository` | SQLite 仓储，管理 sessions、turns、messages、events 四张表 |

### adapters/skill_sources/ - Skill 来源适配

| 组件 | 职责 |
|------|------|
| `SkillMarketplace` | Skill 市场适配器，支持从外部来源获取 skills |

### adapters/plugins/ - 插件系统

| 组件 | 职责 |
|------|------|
| `PluginRegistry` | 插件注册和加载，支持动态扩展系统能力 |

---

## 5. interfaces/ - 接口层

对外暴露的接口，处理协议转换。

### interfaces/http/ - REST API

提供 HTTP REST 端点，用于：
- 会话管理（创建、查询、删除）
- 消息历史查询
- 工具和 Skills 管理
- 系统配置查询

### interfaces/ws/ - WebSocket Gateway

WebSocket 网关，负责：
- 管理多个 Channel
- 在 Channel 和 PublicEventBus 之间路由事件
- 事件格式转换（WebSocket 消息 ↔ EventEnvelope）

---

## 6. app/ - 应用入口层

最外层，负责组装和启动。

| 子模块 | 职责 |
|--------|------|
| `gateway/main.py` | 后端启动入口，初始化和组装所有服务，定义启动/关闭流程 |
| `cli/` | CLI/TUI 客户端，提供终端交互界面 |
| `web/` | Next.js 前端，提供 Web 交互界面 |

---

## 层间通信规则

1. **同层模块**之间可以互相引用（如 `kernel/events/` 和 `kernel/runtime/`）
2. **上层**可以依赖**下层**（如 `adapters/llm/` 使用 `kernel/events/` 的 `EventEnvelope`）
3. **下层不依赖上层**（如 `kernel/` 不 import `adapters/` 或 `interfaces/`）
4. **所有跨模块运行时通信**通过事件总线完成，不直接调用
