# AgentOS 文档索引

欢迎使用 AgentOS 技术文档。本文档详细描述了 AgentOS v0.1 版本的架构设计、技术选型和实现细节。

## 文档结构

### 核心架构
- [01_architecture.md](./01_architecture.md) - 系统架构总览
- [02_event_system.md](./02_event_system.md) - 事件系统设计
- [03_core_modules.md](./03_core_modules.md) - 核心模块详解

### 数据与通信
- [04_database.md](./04_database.md) - 数据库设计
- [05_websocket_protocol.md](./05_websocket_protocol.md) - WebSocket 通信协议

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

在项目根目录创建 `config.yaml`，填入必要的 API Keys。

### 3. 启动服务

```bash
./scripts/dev.sh
```

脚本会自动检查端口占用、配置一致性等问题，并同时启动前端和后端：
- 前端：http://localhost:3000
- 后端：http://localhost:8000

## 核心概念

### 事件驱动架构
AgentOS 采用事件驱动架构，所有模块通过事件总线通信。这种设计提供了良好的解耦性和可扩展性。

### 双总线机制
- **Public Bus**: 全局事件总线
- **Private Bus**: 每个 Agent 的私有总线

Bus Router 负责根据 session_id 路由事件。

### 工具系统
内置 6 种基础工具：
- bash_command: 执行命令
- serper_search: 网络搜索
- fetch_url: 获取网页
- read_file: 读取文件
- write_file: 写入文件
- load_skill: 加载技能

## 技术栈

**前端**:
- Next.js 14 + TypeScript
- React Context API
- shadcn/ui + Tailwind CSS
- 原生 WebSocket

**后端**:
- FastAPI + Python 3.12
- asyncio
- SQLite
- OpenAI / Anthropic SDK

## 版本说明

当前版本: **v0.1**

v0.1 是最小可用版本，专注于核心功能：
- ✅ 基础对话功能
- ✅ 工具调用
- ✅ 会话管理
- ✅ 事件追踪

暂不支持：
- ❌ 流式响应
- ❌ Token 管理
- ❌ 用户认证
- ❌ 沙箱执行

## 贡献指南

欢迎贡献代码和文档！请遵循以下步骤：

1. Fork 项目
2. 创建特性分支
3. 提交变更
4. 发起 Pull Request

## 许可证

待定

## 联系方式

- 项目地址: [待补充]
- 问题反馈: [待补充]
