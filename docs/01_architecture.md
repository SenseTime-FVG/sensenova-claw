# AgentOS 架构设计文档

## 项目概述

AgentOS 是一个基于事件驱动架构的 AI Agent 开发平台，提供 Web 界面和 CLI 客户端。本文档描述当前版本的架构设计和核心特性。

## 核心设计理念

### 事件驱动架构
系统采用事件总线模式，各模块通过发布/订阅事件进行解耦通信。这种设计使得系统具备良好的可扩展性和可维护性。

### Gateway 架构
通过 Gateway 和 Channel 抽象，支持多种用户接入方式：
- **Gateway**: 消息网关，管理多个 Channel 并路由事件
- **Channel**: 用户接入方式的抽象（WebSocket 等）
- **事件路由**: Gateway 在 Channel 和 PublicEventBus 之间双向路由消息

## 技术栈选型

### 前端技术栈
- **框架**: Next.js 14 + TypeScript
- **状态管理**: React Context API
- **通信协议**: 原生 WebSocket
- **UI 组件**: shadcn/ui + Tailwind CSS
- **样式风格**: VS Code 风格的深色主题

### 后端技术栈
- **Web 框架**: FastAPI (Python 3.12)
- **WebSocket**: Starlette WebSocket
- **异步框架**: asyncio
- **事件总线**: 内存队列实现
- **数据存储**: SQLite
- **配置管理**: YAML 格式

### LLM 集成
- **支持的提供商**: OpenAI、OpenAI 兼容服务
- **响应模式**: 非流式（v0.2 版本）
- **模型选择**: 可配置模型

## 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    前端 (Next.js)                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  对话界面    │  │  会话列表    │  │  设置面板    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            │ WebSocket
┌─────────────────────────────────────────────────────────────┐
│                      后端 (FastAPI)                          │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                      Gateway                          │  │
│  │  ┌────────────────┐         ┌────────────────┐      │  │
│  │  │ WebSocket      │         │  CLI 客户端    │      │  │
│  │  │ Channel        │         │  (cli_client)  │      │  │
│  │  └────────────────┘         └────────────────┘      │  │
│  └──────────────────────────────────────────────────────┘  │
│                            │                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                  Public Event Bus                     │  │
│  └──────────────────────────────────────────────────────┘  │
│           │              │              │              │     │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────┐
│  │ Agent      │  │ LLM        │  │ Tool       │  │ Title  │
│  │ Runtime    │  │ Runtime    │  │ Runtime    │  │ Runtime│
│  └────────────┘  └────────────┘  └────────────┘  └────────┘
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Supporting Modules                       │  │
│  │  - ContextBuilder  - SessionStateStore               │  │
│  │  - ToolRegistry    - LLMFactory                      │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                  SQLite Database                      │  │
│  │  - sessions  - turns  - messages  - events           │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## 数据流转示例

用户发送消息的完整流程：

1. 用户在前端/CLI 输入消息
2. Channel 将消息转换为 `ui.user_input` 事件
3. Channel 调用 Gateway.publish_from_channel()
4. Gateway 将事件发布到 Public Bus
5. AgentRuntime 接收事件，发布 `agent.step_started`
6. ContextBuilder 构建 LLM 输入，发布 `llm.call_requested`
7. LLMRuntime 调用 API，发布 `llm.call_result` 和 `llm.call_completed`
8. AgentRuntime 解析响应，如需工具调用则发布 `tool.call_requested`
9. ToolRuntime 执行工具，发布 `tool.call_completed`
10. 循环直到完成，发布 `agent.step_completed`
11. Gateway 订阅 Public Bus，将事件路由到对应 Channel
12. Channel 将结果展示给用户

同时，TitleRuntime 在后台异步为新会话生成标题。

## 本地存储策略

### 存储根目录

存储根目录由配置文件中的 `storage.root` 字段指定，默认值取决于运行模式：

| 模式 | 默认存储根目录 |
|------|---------------|
| 开发模式（`dev`） | `./SenseAssistant`（当前工作目录） |
| 正式模式（`production`） | `~/.SenseAssistant`（用户 home 目录） |

### 会话数据存储
每个会话的工作目录：`<storage.root>/workspace/<session_id>/`

工具结果文件：`<storage.root>/workspace/<session_id>/tool_result_*.txt`

### 日志存储
- 系统日志：`<storage.root>/logs/system.log`
- 会话日志：`<storage.root>/workspace/<session_id>/session.log`

### 数据库位置
- 主数据库：`<storage.root>/agentos.db`

## 安全与权限

### 当前版本策略
- **文件访问**: 无限制（全系统访问）
- **命令执行**: 直接执行，无沙箱
- **工具超时**: 统一 15 秒（可配置）
- **用户认证**: 暂不实现

> ⚠️ 注意：当前版本为开发测试版本，生产环境需要增强安全策略。

## 模块优先级

### 核心模块（已实现）
1. Event Bus（事件总线）
2. AgentRuntime（Agent 运行时）
3. LLMRuntime（LLM 集成）
4. ToolRuntime（工具运行时）
5. TitleRuntime（标题生成）

### 支撑模块（已实现）
6. Gateway（消息网关）
7. WebSocket Channel
8. CLI 客户端
9. ContextBuilder（上下文构建）
10. SessionStateStore（状态管理）
11. Database Layer（数据层）

### 前端模块（已实现）
12. 对话界面
13. WebSocket 客户端
14. 会话列表
15. 设置面板

## 核心特性

### 1. 多 Channel 支持

通过 Gateway 架构，系统可以同时支持多种接入方式：

- **WebSocket Channel**: 为 Web 前端提供实时通信
- **CLI 客户端**: 命令行工具
- **未来扩展**: Slack、Discord、HTTP API 等

每个 Channel 独立管理连接，Gateway 负责事件路由。

### 2. 事件驱动流程

所有模块通过事件通信，主要事件类型：

- `ui.user_input`: 用户输入
- `agent.step_started/completed`: Agent 步骤
- `llm.call_requested/result/completed`: LLM 调用
- `tool.call_requested/started/completed`: 工具调用
- `error.raised`: 错误事件

详见 [02_event_system.md](./02_event_system.md)

### 3. 工具结果截断

当工具返回超长结果时（>16000 tokens），自动：
- 保存完整结果到文件
- 截断并附加文件路径
- 避免 token 超限

### 4. 消息归一化

OpenAI Provider 自动归一化消息格式：
- 添加 `type: "function"` 到 tool_calls
- 确保 tool 消息包含 tool_call_id
- 转换 arguments 为 JSON 字符串

避免 API 调用失败（如 400 invalid_value）。

### 5. 自动标题生成

TitleRuntime 为新会话自动生成简短标题：
- 异步执行，不阻塞主流程
- 使用独立 LLM 调用
- 失败时不影响系统运行

## 扩展性考虑

虽然当前版本功能已较完善，但架构设计已为未来扩展预留空间：

- 流式响应支持
- 多模型动态切换
- Token 管理和计费
- 用户认证系统
- 沙箱执行环境
- 分布式事件总线（Redis）
- 多 Agent 协作
- Skill 真实执行引擎

## 版本历史

### v0.2（当前）
- ✅ Gateway 架构
- ✅ CLI 客户端支持
- ✅ 自动标题生成
- ✅ 工具结果截断
- ✅ 消息归一化

### v0.1
- ✅ 基础对话功能
- ✅ 工具调用
- ✅ 会话管理
- ✅ 事件追踪
