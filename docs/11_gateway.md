# Gateway 架构设计

## 概述

Gateway 模块是 AgentOS 的消息网关层，负责接收来自不同 Channel 的消息，并将消息路由到 PublicEventBus，同时将 PublicEventBus 上的事件分发给对应的 Channel。

## 核心概念

### Gateway

Gateway 是消息网关的核心组件，负责：
- 管理多个 Channel 的生命周期
- 接收来自各个 Channel 的消息并转发到 PublicEventBus
- 订阅 PublicEventBus 上的事件并分发给对应的 Channel
- 维护 session 与 Channel 的绑定关系

### Channel

Channel 是用户消息来源的抽象，代表不同的访问方式。每个 Channel 负责：
- 接收来自特定来源的用户输入
- 将用户输入转换为标准的事件格式
- 接收来自 Gateway 的事件并展示给用户
- 管理与用户的连接状态

## 架构设计

```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  WebSocket      │  │  CLI Client     │  │  Future         │
│  Channel        │  │  (cli_client)   │  │  Channels       │
│  - Web 前端     │  │  - 命令行工具   │  │  - Slack        │
│  - HTTP/WS      │  │  - WebSocket    │  │  - Discord      │
└─────────────────┘  └─────────────────┘  └─────────────────┘
         ↕                    ↕                    ↕
┌─────────────────────────────────────────────────────────────┐
│                         Gateway                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           Channel Manager                             │  │
│  │  - 管理 Channel 生命周期                              │  │
│  │  - 维护 session 与 Channel 的映射                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                           ↕                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           Event Router                                │  │
│  │  - 接收 Channel 消息 → PublicEventBus                │  │
│  │  - 订阅 PublicEventBus → 分发到 Channel              │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘


```

## Channel 接口定义

```python
class Channel(ABC):
    @abstractmethod
    async def start(self) -> None:
        """启动 Channel"""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """停止 Channel"""
        pass

    @abstractmethod
    async def send_event(self, event: EventEnvelope) -> None:
        """接收来自 Gateway 的事件并发送给用户"""
        pass

    @abstractmethod
    def get_channel_id(self) -> str:
        """获取 Channel 的唯一标识"""
        pass
```

## 消息流转

### 用户输入流程

1. 用户通过 Channel 发送消息（如 Web 前端输入、CLI 客户端输入）
2. Channel 将消息转换为 `UI_USER_INPUT` 事件
3. Channel 调用 Gateway 的 `publish_from_channel()` 方法
4. Gateway 将事件发布到 PublicEventBus
5. AgentRuntime 等模块处理事件

### 事件分发流程

1. AgentRuntime/LLMRuntime/ToolRuntime 发布事件到 PublicEventBus
2. Gateway 订阅 PublicEventBus 上的事件
3. Gateway 根据 session_id 找到对应的 Channel
4. Gateway 调用 Channel 的 `send_event()` 方法
5. Channel 将事件展示给用户

## 实现要点

### Session 绑定

Gateway 需要维护 session_id 与 Channel 的映射关系：

```python
class Gateway:
    def __init__(self):
        self._session_bindings: dict[str, Channel] = {}

    def bind_session(self, session_id: str, channel: Channel) -> None:
        """绑定 session 到 Channel"""
        self._session_bindings[session_id] = channel

    def unbind_session(self, session_id: str) -> None:
        """解绑 session"""
        self._session_bindings.pop(session_id, None)
```

### 事件过滤

Gateway不处理事件过滤，channel模块来决定自己需要哪些事件

### 错误处理

- Channel 连接断开时，Gateway 应该清理相关的 session 绑定
- Channel 发送失败时，应该记录日志但不影响其他 Channel
- Gateway 应该能够优雅地处理 Channel 的启动和停止

## CLI 客户端实现

使用 Python 实现的命令行客户端，通过 WebSocket 连接到 Gateway：

### 功能特性

- 实时显示对话消息
- 支持用户输入
- 显示工具调用状态
- 简洁的命令行界面

### 使用方法

```bash
cd backend
python3 cli_client.py --host localhost --port 8000
```

### 实现说明

CLI 客户端作为独立进程运行，通过 WebSocket 协议连接到 Gateway，不需要在 Gateway 中注册为 Channel。

## 实现步骤

### Phase 1: Gateway 核心

1. 创建 `app/gateway/base.py` - 定义 Gateway 和 Channel 接口
2. 创建 `app/gateway/gateway.py` - 实现 Gateway 核心逻辑
3. 重构现有的 WebSocketForwarder 为 WebSocketChannel

### Phase 2: CLI 客户端

1. 创建 `cli_client.py` - 实现 CLI 客户端
2. 通过 WebSocket 连接到 Gateway
3. 实现消息显示和用户输入

### Phase 3: 集成

1. 在 `main.py` 中集成 Gateway
2. 启动 WebSocket Channel
3. CLI 客户端独立运行，连接到 Gateway

## 配置示例

```yaml
gateway:
  channels:
    - type: websocket
      enabled: true
      port: 8000
```

## 未来扩展

### 支持更多 Channel

- **Feishu Channel**
- **HTTP API Channel**

### 高级特性

- Channel 级别的权限控制
- 消息格式转换和适配
- 多租户支持
- 消息队列和持久化

## 总结

Gateway 架构将消息来源抽象为 Channel，使得 AgentOS 可以轻松支持多种访问方式。通过统一的事件总线和标准的 Channel 接口，系统具有良好的扩展性和可维护性。
