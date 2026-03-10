# AgentOS 文档索引

欢迎使用 AgentOS 技术文档。本文档详细描述了 AgentOS 的架构设计、技术选型和实现细节。

## 文档结构

### 核心架构
- [01_architecture.md](./01_architecture.md) - 系统架构总览
- [02_event_system.md](./02_event_system.md) - 事件系统设计
- [03_core_modules.md](./03_core_modules.md) - 核心模块详解（AgentRuntime、LLMRuntime、ToolRuntime等）

### 数据与通信
- [04_database.md](./04_database.md) - 数据库设计
- [05_websocket_protocol.md](./05_websocket_protocol.md) - WebSocket 通信协议
- [11_gateway.md](./11_gateway.md) - Gateway 架构设计（多 Channel 支持）

### 工具与技能系统
- [12_builtin_tools.md](./12_builtin_tools.md) - 内置工具文档（bash_command、serper_search等）
- [13_skills_system.md](./13_skills_system.md) - Skills 系统设计（声明式任务编排）

### 演进规划（PRD）
- [14_dual_bus_architecture.md](./14_dual_bus_architecture.md) - 双总线架构（Public + Private Bus + 轻量 Worker）
- [15_event_standardization.md](./15_event_standardization.md) - 事件系统标准化（生命周期对称 + 命名规范）
- [16_tool_system_enhancement.md](./16_tool_system_enhancement.md) - 工具系统增强（权限管理 + 截断统一 + write_file 增强）
- [17_system_prompt_workspace_session.md](./17_system_prompt_workspace_session.md) - System Prompt 模块化 + Workspace 文件体系 + Session 持久化增强
- [18_memory_system.md](./18_memory_system.md) - 长期记忆系统（文件记忆 + 语义搜索 + MEMORY.md 注入）

### 前端与配置
- [06_frontend_architecture.md](./06_frontend_architecture.md) - 前端架构设计
- [07_configuration.md](./07_configuration.md) - 配置文件设计

### 开发与部署
- [08_development_guide.md](./08_development_guide.md) - 开发指南
- [09_deployment.md](./09_deployment.md) - 部署指南
- [10_technical_decisions.md](./10_technical_decisions.md) - 技术决策记录

## 快速开始

### 1. 环境准备

```bash
# 安装后端依赖
cd backend && uv sync

# 安装前端依赖
cd frontend && npm install
```

### 2. 配置

在项目根目录创建 `config.yaml`，填入必要的 API Keys：

```yaml
agent:
  provider: openai
  default_model: gpt-5.2
  default_temperature: 0.6
  system_prompt: "你是一个有用的AI助手"

tools:
  serper_search:
    api_key: "your_serper_api_key"

llm:
  openai:
    api_key: "your_openai_api_key"
```

### 3. 启动服务

```bash
# 一键启动前后端
npm run dev

# 或分别启动
cd backend && uv run python3 main.py
cd frontend && npm run dev
```

服务地址：
- 前端：http://localhost:3000
- 后端：http://localhost:8000

### 4. CLI 客户端

除了 Web 界面，还可以使用命令行客户端：

```bash
cd backend
python3 cli_client.py --host localhost --port 8000
```

## 核心概念

### 事件驱动架构
AgentOS 采用事件驱动架构，所有模块通过事件总线通信。这种设计提供了良好的解耦性和可扩展性。

### Gateway 与 Channel
- **Gateway**: 消息网关，管理多个 Channel
- **Channel**: 用户接入方式的抽象（WebSocket、未来可扩展 CLI、Slack 等）
- **事件路由**: Gateway 负责在 Channel 和 PublicEventBus 之间路由消息

### 核心 Runtime 模块
- **AgentRuntime**: 对话流程编排
- **LLMRuntime**: LLM 调用管理
- **ToolRuntime**: 工具执行管理
- **TitleRuntime**: 会话标题生成

### 工具系统
内置 5 种基础工具：
- `bash_command`: 执行命令
- `serper_search`: 网络搜索
- `fetch_url`: 获取网页
- `read_file`: 读取文件
- `write_file`: 写入文件

详见 [12_builtin_tools.md](./12_builtin_tools.md)

### Skills 系统
16 个内置 skills 提供声明式任务编排能力，包括：
- PDF/DOCX/XLSX 文档处理
- 前端设计与测试
- Skill 创建工具

详见 [13_skills_system.md](./13_skills_system.md)

## 技术栈

**前端**:
- Next.js 14 + TypeScript
- React Context API
- shadcn/ui + Tailwind CSS
- 原生 WebSocket

**后端**:
- FastAPI + Python 3.12
- asyncio 事件驱动
- SQLite 数据存储
- OpenAI / Anthropic SDK


## 架构特点

### 1. 事件驱动
所有模块通过事件总线解耦，易于扩展和测试。

### 2. 多 Channel 支持
通过 Gateway 架构支持多种接入方式：
- WebSocket Channel（Web 前端）
- CLI 客户端（命令行工具）
- 未来可扩展：Slack、Discord、HTTP API 等

### 3. 状态管理
- 内存状态：SessionStateStore 管理运行时状态
- 持久化：SQLite 存储会话、消息、事件

### 4. 工具结果截断
自动处理超长工具结果，避免 token 超限。

### 5. 消息归一化
OpenAI Provider 自动归一化消息格式，避免 API 调用失败。

## 版本说明

当前版本: **v0.4**

v0.4 新增特性：
- ✅ Skills 系统（声明式任务编排）
- ✅ 16 个内置 skills（PDF、DOCX、前端设计等）
- ✅ Skills 配置管理
- ✅ 移除占位 Tools（search_skill、load_skill）

v0.2 新增特性：
- ✅ Gateway 架构
- ✅ CLI 客户端支持
- ✅ 自动标题生成
- ✅ 工具结果截断
- ✅ 消息归一化

v0.1 核心功能：
- ✅ 基础对话功能
- ✅ 工具调用
- ✅ 会话管理
- ✅ 事件追踪

暂不支持：
- ❌ 流式响应
- ❌ Token 管理
- ❌ 用户认证
- ❌ 沙箱执行

## 开发指南

### 运行测试

```bash
# 后端测试
cd backend
uv run python3 -m pytest

# 前端测试
cd frontend
npm run test:e2e
```

### 日志查看

开发模式下，后端会输出 DEBUG 级别日志，包括：
- 每次 LLM 调用的完整输入
- 工具执行详情
- 事件流转追踪

### 添加自定义工具

参考 [12_builtin_tools.md](./12_builtin_tools.md) 中的"扩展自定义工具"章节。

## 贡献指南

欢迎贡献代码和文档！请遵循以下步骤：

1. Fork 项目
2. 创建特性分支
3. 提交变更
4. 发起 Pull Request

## 文档维护

- `docs_raw/`: 用户手动维护的原始文档，不要修改
- `docs/`: 模型生成的技术文档，可以修改和更新

## 许可证

待定

## 联系方式

- 项目地址: [待补充]
- 问题反馈: [待补充]
