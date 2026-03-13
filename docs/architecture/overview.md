# 系统架构总览

## AgentOS 简介

AgentOS 是一个基于**事件驱动架构**的 AI Agent 平台，支持 Web、CLI、TUI 多种接入方式。其核心设计理念是：**所有模块通过事件总线解耦通信**，事件封装为统一的 `EventEnvelope` 数据结构，模块之间不存在直接方法调用。

## 整体架构

AgentOS 的请求处理链路如下：

```
用户请求
  │
  ▼
Channel（WebSocket / CLI / TUI / 飞书）
  │
  ▼
Gateway（事件入口）
  │
  ▼
PublicEventBus（全局事件广播）
  │
  ▼
BusRouter（按 session_id 路由）
  │
  ▼
PrivateEventBus（每 session 一个，物理隔离）
  │
  ▼
Worker（AgentSessionWorker / LLMSessionWorker / ToolSessionWorker）
  │
  ▼
产生新事件 → 回流到 PublicEventBus → 继续路由
```

### 模块关系总览

| 层级 | 模块 | 职责 |
|------|------|------|
| **应用入口** | `app/gateway/main.py` | 后端启动入口，初始化所有服务 |
| **接口层** | `interfaces/http/`, `interfaces/ws/` | REST API、WebSocket Gateway |
| **适配层** | `adapters/llm/`, `adapters/channels/`, `adapters/storage/` | LLM 提供商、Channel 适配、数据库仓储 |
| **能力层** | `capabilities/tools/`, `capabilities/skills/`, `capabilities/agents/` | 工具系统、Skills 系统、多 Agent 配置 |
| **核心内核** | `kernel/events/`, `kernel/runtime/` | 事件系统、Runtime-Worker 机制 |
| **平台层** | `platform/config/`, `platform/security/` | 配置加载、安全策略 |

## 核心事件流

一次完整的用户对话请求，在系统内的事件流转如下：

```
user.input
  │
  ▼
agent.step_started
  │
  ▼
llm.call_requested ──► llm.call_started ──► llm.call_result ──► llm.call_completed
  │
  ▼（如果 LLM 返回了 tool_calls）
tool.call_requested ──► tool.call_started ──► tool.call_result ──► tool.call_completed
  │
  ▼（工具结果收集完毕后，再次发起 LLM 调用）
llm.call_requested ──► ... ──► llm.call_result（无 tool_calls，stop）
  │
  ▼
agent.step_completed
```

这个循环会一直持续，直到 LLM 返回不包含 `tool_calls` 的最终回复。

## 关键设计决策

### asyncio 单进程

AgentOS 基于 Python `asyncio` 实现并发，所有 Runtime 和 Worker 以协程方式运行在同一个事件循环中。这带来了以下好处：

- 无需处理多进程间通信和同步
- 事件总线可以使用简单的 `asyncio.Queue` 实现
- 内存状态共享无需加锁（单线程协程模型）

### SQLite 持久化

选用 SQLite 作为持久化存储，原因：

- 零部署成本，无需独立数据库服务
- 在当前环境中比 `aiosqlite` 更稳定
- 满足单机部署场景的需求

### 内存状态 + 数据库持久化双层设计

- **内存层**（`SessionStateStore`）：维护当前活跃会话的热数据，包括轮次状态、消息历史、待处理工具调用
- **持久化层**（SQLite `Repository`）：存储会话、轮次、消息、事件的完整历史

内存层提供快速读写，持久化层确保数据不丢失。首轮对话时从 SQLite 加载历史到内存，后续操作在内存中完成，关键节点写回数据库。

### 事件驱动解耦

所有模块之间不存在直接方法调用，统一通过事件通信。这意味着：

- 新增功能只需订阅/发布事件，无需修改已有模块
- 各模块可以独立测试（注入事件、断言输出事件）
- 事件天然可持久化、可回放、可审计
